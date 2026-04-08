"""
Scrape le McGill Course Catalogue pour le programme Major in Computer Science.

Stratégie :
  1. Page programme → extraire tous les cours listés dans les tables sc_courselist
     (COMP, MATH et tout autre sigle) — ce sont les cours du périmètre principal.
  2. Pour chaque cours → page individuelle → titre, crédits, description,
     préalables, corequis, équivalences.
  3. Prérequis référencés mais absents du programme → hors-périmètre, fetchés aussi.

Sauvegarde dans etl/mcgill/raw_courses.json.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL    = "https://coursecatalogue.mcgill.ca"
PROGRAM_URL = (
    f"{BASE_URL}/en/undergraduate/science/programs/computer-science"
    "/computer-science-major-bsc/"
)
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

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

COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s+(\d{3}[A-Z0-9]*)\b")


# ── Page programme ────────────────────────────────────────────────────────────

def fetch_program_courses() -> list[tuple[str, str]]:
    """
    Retourne la liste (course_id, course_url) de tous les cours listés
    dans le programme (tables sc_courselist), tous sujets confondus.
    """
    print(f"Fetching programme : {PROGRAM_URL}")
    resp = SESSION.get(PROGRAM_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    for table in soup.find_all("table", class_="sc_courselist"):
        for tr in table.find_all("tr"):
            code_td = tr.find("td", class_="codecol")
            if not code_td:
                continue
            code = re.sub(r"\s+", " ", code_td.get_text(strip=True))
            if not re.match(r"^[A-Z]{2,5}\s+\d{3}", code):
                continue
            if code in seen:
                continue
            seen.add(code)

            # URL de la page individuelle depuis le bubbledrawer
            drawer = tr.find_next_sibling("tr", class_="bubbledrawer")
            url = ""
            if drawer:
                a = drawer.find("a", href=re.compile(r"/courses/"))
                if a:
                    url = a["href"]
                    if not url.startswith("http"):
                        url = BASE_URL + url

            result.append((code, url))

    return result


# ── Page individuelle ─────────────────────────────────────────────────────────

def slug(course_id: str) -> str:
    """'COMP 202' → 'comp-202'"""
    return course_id.lower().replace(" ", "-")


def parse_note_texts(soup: BeautifulSoup) -> tuple[list[str], list[str], list[str], str]:
    """
    Extrait prerequisite_courses, concomitant_courses, equivalent_courses
    et requirement_text depuis les éléments .detail-note_text.
    """
    prereqs:   list[str] = []
    coreqs:    list[str] = []
    equivs:    list[str] = []
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


def fetch_course(course_id: str, url: str = "") -> Optional[dict]:
    if not url:
        url = f"{BASE_URL}/courses/{slug(course_id)}/index.html"
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ {course_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.find("h1", class_="page-title")
    if not h1:
        return None
    title_text = h1.get_text(" ", strip=True)
    name = re.sub(r"^[A-Z]+\s+\d{3}[A-Z0-9]*\.\s*", "", title_text).rstrip(".")

    credits_el = soup.select_one(".detail-credits .value")
    credits = float(credits_el.get_text(strip=True)) if credits_el else 0.0

    desc_el = soup.select_one(".section--description .section__content")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    prereqs, coreqs, equivs, req_text = parse_note_texts(soup)

    return {
        "id":                   course_id,
        "name":                 name,
        "credits":              credits,
        "description":          description,
        "prerequisite_courses": prereqs,
        "concomitant_courses":  coreqs,
        "equivalent_courses":   equivs,
        "requirement_text":     req_text,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Cours du programme
    program_list = fetch_program_courses()
    print(f"  {len(program_list)} cours dans le programme.\n")

    program_courses: list[dict] = []
    for i, (code, url) in enumerate(program_list, 1):
        course = fetch_course(code, url)
        if course:
            program_courses.append(course)
            print(f"  [{i:2d}/{len(program_list)}] ✓ {code} — {course['name'][:50]}")
        else:
            print(f"  [{i:2d}/{len(program_list)}] ✗ {code} (404)")
        time.sleep(0.3)

    # 2. Prérequis hors-périmètre
    program_ids = {c["id"] for c in program_courses}
    other_ids: set[str] = set()
    for c in program_courses:
        for dep in c["prerequisite_courses"] + c["concomitant_courses"]:
            if dep not in program_ids:
                other_ids.add(dep)

    print(f"\n{len(other_ids)} cours hors-périmètre référencés comme prérequis.")
    other_courses: list[dict] = []
    for i, code in enumerate(sorted(other_ids), 1):
        course = fetch_course(code)
        if course:
            other_courses.append(course)
            print(f"  [{i:2d}/{len(other_ids)}] ✓ {code} — {course['name'][:50]}")
        else:
            # Cours introuvable : stub minimal
            other_courses.append({
                "id": code, "name": "", "credits": 0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            })
            print(f"  [{i:2d}/{len(other_ids)}] ✗ {code} (404 — stub)")
        time.sleep(0.3)

    # 3. Sauvegarder
    result = {
        "metadata": {
            "source":        "McGill Course Catalogue – Major in Computer Science",
            "program_url":   PROGRAM_URL,
            "program_count": len(program_courses),
            "other_count":   len(other_courses),
        },
        "courses": {
            "PROGRAM": program_courses,
            "OTHER":   other_courses,
        },
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  PROGRAM: {len(program_courses)} cours")
    print(f"  OTHER:   {len(other_courses)} cours hors-périmètre")
    subjects = sorted({c["id"].split()[0] for c in program_courses})
    print(f"  Sujets dans le programme : {subjects}")


if __name__ == "__main__":
    main()
