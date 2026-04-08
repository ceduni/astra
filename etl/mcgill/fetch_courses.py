"""
Scrape le McGill Course Catalogue (https://coursecatalogue.mcgill.ca) pour
tous les cours COMP.

Sources de découverte :
  1. Les codes COMP extraits du PDF (etl/mcgill/raw_courses.json existant)
  2. L'index A-Z du catalogue pour compléter

Pour chaque cours COMP, récupère :
  id, name, credits, description, prerequisite_courses,
  concomitant_courses, equivalent_courses, requirement_text

Sauvegarde dans etl/mcgill/raw_courses.json (même schéma que etl/udem/).
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL    = "https://coursecatalogue.mcgill.ca"
AZ_URL      = f"{BASE_URL}/azindex/"
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"
PDF_JSON    = Path(__file__).parent / "raw_courses.json"  # codes déjà extraits du PDF

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Regex pour extraire les codes de cours (ex: COMP 202, MATH 240, ECSE 321)
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,4})\s+(\d{3}[A-Z0-9]*)\b")


# ── Découverte ────────────────────────────────────────────────────────────────

def slug(course_id: str) -> str:
    """'COMP 202' → 'comp-202'"""
    return course_id.lower().replace(" ", "-")


def load_pdf_codes() -> set[str]:
    """Charge les codes COMP déjà extraits du PDF."""
    if not PDF_JSON.exists():
        return set()
    data = json.loads(PDF_JSON.read_text())
    return {c["id"] for c in data.get("courses", {}).get("COMP", [])}


def fetch_az_comp_codes() -> set[str]:
    """Scrape l'index A-Z pour trouver tous les cours COMP."""
    print("Fetching AZ index...")
    resp = SESSION.get(AZ_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    codes = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.match(r"^/courses/comp-(\d{3}[a-z0-9]*)/?$", href)
        if m:
            code = m.group(1).upper()
            codes.add(f"COMP {code}")
    print(f"  {len(codes)} cours COMP trouvés dans l'index A-Z.")
    return codes


# ── Scraping d'une page de cours ──────────────────────────────────────────────

def parse_note_texts(soup: BeautifulSoup) -> tuple[list[str], list[str], list[str], str]:
    """
    Extrait prerequisite_courses, concomitant_courses, equivalent_courses
    et requirement_text depuis les éléments .detail-note_text.
    """
    prereqs:  list[str] = []
    coreqs:   list[str] = []
    equivs:   list[str] = []
    req_parts: list[str] = []

    note_items = soup.select(".detail-note_text li, .detail-note_text p")
    for item in note_items:
        text = item.get_text(" ", strip=True)
        if not text:
            continue
        req_parts.append(text)
        lower = text.lower()

        if lower.startswith("prerequisite"):
            for m in COURSE_CODE_RE.finditer(text):
                prereqs.append(f"{m.group(1)} {m.group(2)}")
        elif lower.startswith("corequisite") or lower.startswith("co-requisite"):
            for m in COURSE_CODE_RE.finditer(text):
                coreqs.append(f"{m.group(1)} {m.group(2)}")
        elif lower.startswith("equivalent") or "equivalen" in lower:
            for m in COURSE_CODE_RE.finditer(text):
                equivs.append(f"{m.group(1)} {m.group(2)}")

    return (
        list(dict.fromkeys(prereqs)),
        list(dict.fromkeys(coreqs)),
        list(dict.fromkeys(equivs)),
        " | ".join(req_parts),
    )


def fetch_course(course_id: str) -> Optional[dict]:
    url = f"{BASE_URL}/courses/{slug(course_id)}/"
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ {course_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Titre (ex: "COMP 202. Foundations of Programming.")
    h1 = soup.find("h1", class_="page-title")
    if not h1:
        return None
    title_text = h1.get_text(" ", strip=True)
    # Retire le sigle du début : "COMP 202. Foundations of Programming." → "Foundations of Programming"
    name = re.sub(r"^[A-Z]+\s+\d{3}[A-Z0-9]*\.\s*", "", title_text).rstrip(".")

    # Crédits
    credits_el = soup.select_one(".detail-credits .value")
    credits = float(credits_el.get_text(strip=True)) if credits_el else 0.0

    # Description
    desc_el = soup.select_one(".section--description .section__content")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    # Notes (prérequis, corequis, équivalences)
    prereqs, coreqs, equivs, req_text = parse_note_texts(soup)

    return {
        "id":                  course_id,
        "name":                name,
        "credits":             credits,
        "description":         description,
        "prerequisite_courses":  prereqs,
        "concomitant_courses":   coreqs,
        "equivalent_courses":    equivs,
        "requirement_text":      req_text,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Collecter tous les codes COMP à scraper
    pdf_codes = load_pdf_codes()
    az_codes  = fetch_az_comp_codes()
    all_codes = sorted(pdf_codes | az_codes)
    print(f"\n{len(all_codes)} cours COMP à scraper "
          f"(PDF: {len(pdf_codes)}, A-Z: {len(az_codes)}, "
          f"union: {len(all_codes)}).\n")

    # 2. Scraper chaque cours
    comp_courses: list[dict] = []
    for i, code in enumerate(all_codes, 1):
        course = fetch_course(code)
        if course:
            comp_courses.append(course)
            print(f"  [{i:3d}/{len(all_codes)}] ✓ {code} — {course['name'][:50]}")
        else:
            print(f"  [{i:3d}/{len(all_codes)}] ✗ {code} (404)")
        time.sleep(0.3)

    # 3. Collecter les prérequis hors-périmètre (non-COMP référencés)
    comp_ids = {c["id"] for c in comp_courses}
    other_ids: set[str] = set()
    for c in comp_courses:
        for code in c["prerequisite_courses"] + c["concomitant_courses"]:
            if code not in comp_ids:
                other_ids.add(code)

    print(f"\n{len(other_ids)} cours hors-périmètre référencés comme prérequis.")
    other_courses: list[dict] = []
    for i, code in enumerate(sorted(other_ids), 1):
        course = fetch_course(code)
        if course:
            other_courses.append(course)
            print(f"  [{i:3d}/{len(other_ids)}] ✓ {code} — {course['name'][:50]}")
        else:
            print(f"  [{i:3d}/{len(other_ids)}] ✗ {code} (404)")
        time.sleep(0.3)

    # 4. Sauvegarder
    result = {
        "metadata": {
            "source":       "McGill Course Catalogue – coursecatalogue.mcgill.ca",
            "base_url":     BASE_URL,
            "comp_count":   len(comp_courses),
            "other_count":  len(other_courses),
        },
        "courses": {
            "COMP":  comp_courses,
            "OTHER": other_courses,
        },
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  COMP:  {len(comp_courses)} cours")
    print(f"  OTHER: {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
