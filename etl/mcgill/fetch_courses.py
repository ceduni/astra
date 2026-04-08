"""
Scrape le McGill Course Catalogue pour le programme Major in Computer Science.

Stratégie :
  1. Page programme → extraire les cours explicitement listés dans les tables
     sc_courselist (required + complementary options nommées : COMP + MATH).
  2. Page /courses/ → extraire tous les cours COMP 300-499 éligibles comme
     complémentaires (sauf COMP 396). Ces cours + ceux de l'étape 1 forment
     le périmètre du programme (hors_perimetre: false).
  3. Pour chaque cours du périmètre → page individuelle → titre, crédits,
     description, prérequis, corequis, équivalences.
  4. Prérequis référencés absents du périmètre → hors_perimetre: true.

Sauvegarde dans etl/mcgill/raw_courses.json.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL     = "https://coursecatalogue.mcgill.ca"
PROGRAM_URL  = (
    f"{BASE_URL}/en/undergraduate/science/programs/computer-science"
    "/computer-science-major-bsc/"
)
COURSES_URL  = f"{BASE_URL}/courses/"
OUTPUT_FILE  = Path(__file__).parent / "raw_courses.json"

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

# Cours exclu explicitement par le programme
EXCLUDED = {"COMP 396"}


# ── Découverte ────────────────────────────────────────────────────────────────

def fetch_program_explicit() -> list[tuple[str, str]]:
    """
    Retourne (course_id, page_url) pour tous les cours listés explicitement
    dans les tables sc_courselist de la page programme.
    """
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
            if code in seen or code in EXCLUDED:
                continue
            seen.add(code)

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


def fetch_comp_electives() -> list[tuple[str, str]]:
    """
    Retourne (course_id, page_url) pour tous les cours COMP 300-499 du catalogue
    (éligibles comme complémentaires), sauf ceux dans EXCLUDED.
    """
    resp = SESSION.get(COURSES_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=True):
        m = re.match(r"^.*/courses/(comp-(\d+[a-z0-9]*))/index\.html$", a["href"])
        if not m:
            continue
        slug = m.group(1)
        num_str = m.group(2).upper()
        # keep only 300-499 (undergrad electives)
        num = int(re.match(r"\d+", num_str).group())
        if num < 300 or num >= 500:
            continue
        code = f"COMP {num_str}"
        if code in seen or code in EXCLUDED:
            continue
        seen.add(code)
        url = BASE_URL + re.sub(r"index\.html$", "", a["href"])
        result.append((code, url))

    return sorted(result, key=lambda x: x[0])


# ── Scraping d'une page de cours ──────────────────────────────────────────────

def parse_note_texts(soup: BeautifulSoup) -> tuple[list[str], list[str], list[str], str]:
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
        slug = course_id.lower().replace(" ", "-")
        url = f"{BASE_URL}/courses/{slug}/"
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
    # 1. Cours explicitement listés dans le programme
    print(f"Fetching programme page : {PROGRAM_URL}")
    explicit = fetch_program_explicit()
    print(f"  {len(explicit)} cours explicitement listés.")

    # 2. Cours COMP 300-499 éligibles comme complémentaires
    print(f"\nFetching COMP 300-499 electives from {COURSES_URL}")
    electives = fetch_comp_electives()
    explicit_ids = {code for code, _ in explicit}
    electives = [(c, u) for c, u in electives if c not in explicit_ids]
    print(f"  {len(electives)} cours COMP 300-499 additionnels.")

    # Union ordonnée : explicites d'abord, puis complémentaires
    all_program = explicit + electives
    print(f"\nTotal périmètre programme : {len(all_program)} cours.\n")

    # 3. Scraper chaque cours du périmètre
    program_courses: list[dict] = []
    for i, (code, url) in enumerate(all_program, 1):
        course = fetch_course(code, url)
        if course:
            program_courses.append(course)
            print(f"  [{i:2d}/{len(all_program)}] ✓ {code} — {course['name'][:50]}")
        else:
            print(f"  [{i:2d}/{len(all_program)}] ✗ {code} (404)")
        time.sleep(0.25)

    # 4. Prérequis hors-périmètre
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
            other_courses.append({
                "id": code, "name": "", "credits": 0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            })
            print(f"  [{i:2d}/{len(other_ids)}] ✗ {code} (404 — stub)")
        time.sleep(0.25)

    # 5. Sauvegarder
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
    subjects = sorted({c["id"].split()[0] for c in program_courses})
    print(f"  Sujets  : {subjects}")
    print(f"  OTHER   : {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
