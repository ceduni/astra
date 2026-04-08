"""
Scrape le programme 7617 (Baccalauréat en informatique) de l'UQAM.

Stratégie :
  1. Page programme → extraire tous les sigles listés dans TOUS les blocs
     (Informatique obligatoire, Mathématiques, Sciences de la gestion,
     Éthique, Activité de synthèse, Cours au choix, Coopératif, Honor).
     → Ce sont les cours du périmètre (hors_perimetre: false).
  2. Pour chaque sigle → page individuelle → titre, crédits, description,
     préalables académiques.
  3. Prérequis référencés mais absents du périmètre → hors_perimetre: true.

Note : les pages individuelles sont server-side rendered ; requests suffit.

Sauvegarde dans etl/uqam/raw_courses.json.
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROGRAM_URL   = "https://etudier.uqam.ca/programme?code=7617"
COURSE_URL    = "https://etudier.uqam.ca/cours?sigle={sigle}"
OUTPUT_FILE   = Path(__file__).parent / "raw_courses.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

SIGLE_RE  = re.compile(r"^([A-Z]{2,4})(\d{4}[A-Z0-9]*)$")
PREREQ_RE = re.compile(r"\[([A-Z]{2,4}\d{4}[A-Z0-9]*)")

KNOWN_SECTIONS = {
    "Objectifs", "Sommaire du contenu", "Modalité d'enseignement",
    "Préalables académiques", "Concomitants", "Préalables cours",
    "Préalables autres", "Programmes associés à ce cours",
    "Cycle", "Type de cours", "Nombre de crédits", "Discipline",
}


# ── Page programme ────────────────────────────────────────────────────────────

def fetch_program_sigles() -> list[str]:
    """
    Retourne tous les sigles du programme, dans l'ordre d'apparition,
    tous blocs confondus (obligatoires + optionnels + coopératif + honor).
    """
    resp = SESSION.get(PROGRAM_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    sigles: list[str] = []
    seen:   set[str]  = set()

    for el in soup.select("div.ligne_cours[data-sigle]"):
        sigle = el["data-sigle"].strip()
        if SIGLE_RE.match(sigle) and sigle not in seen:
            seen.add(sigle)
            sigles.append(sigle)

    return sigles


# ── Page individuelle ─────────────────────────────────────────────────────────

def parse_course_page(sigle: str) -> dict:
    resp = SESSION.get(COURSE_URL.format(sigle=sigle), timeout=30)
    if resp.status_code == 404:
        return _stub(sigle)
    resp.raise_for_status()

    soup      = BeautifulSoup(resp.text, "html.parser")
    desc_div  = soup.find(id="description")
    if desc_div is None:
        return _stub(sigle)

    full_text = desc_div.get_text("\n", strip=True)
    lines     = [l.strip() for l in full_text.splitlines() if l.strip()]

    # Titre depuis <h1>
    h1   = soup.find("h1", class_="title")
    name = ""
    if h1:
        h1_text = h1.get_text(" ", strip=True)
        name    = re.sub(r"^.*?//\s*[A-Za-z]{2,4}\d{4}\S*\s*-\s*", "", h1_text,
                         flags=re.IGNORECASE).strip()

    # Crédits (label et valeur sur deux lignes distinctes)
    credits = 0
    for i, line in enumerate(lines):
        if "Nombre de crédits" in line:
            m = re.search(r":\s*(\d+)", line)
            if not m and i + 1 < len(lines):
                m = re.search(r":\s*(\d+)", lines[i + 1])
            if m:
                credits = int(m.group(1))
            break

    description = _extract_section(lines, ["Objectifs", "Sommaire du contenu"])
    prereqs, req_text = _extract_prereqs(lines)

    return {
        "id":                   sigle,
        "name":                 name,
        "credits":              credits,
        "description":          description,
        "prerequisite_courses": prereqs,
        "concomitant_courses":  [],
        "equivalent_courses":   [],
        "requirement_text":     req_text,
    }


def _extract_section(lines: list[str], section_names: list[str]) -> str:
    collecting = False
    parts: list[str] = []
    for line in lines:
        is_header = line in KNOWN_SECTIONS
        if line in section_names:
            collecting = True
            continue
        if is_header and collecting:
            if line in section_names:
                continue
            collecting = False
        if collecting and not is_header:
            parts.append(line)
    return " ".join(parts).strip()


def _extract_prereqs(lines: list[str]) -> tuple[list[str], str]:
    in_section = False
    req_lines: list[str] = []
    for line in lines:
        if line == "Préalables académiques":
            in_section = True
            continue
        if in_section:
            if line in {"Objectifs", "Sommaire du contenu", "Modalité d'enseignement",
                        "Concomitants", "Préalables cours", "Préalables autres",
                        "Programmes associés à ce cours"}:
                break
            req_lines.append(line)
    req_text = " ".join(req_lines).strip()
    prereqs  = list(dict.fromkeys(PREREQ_RE.findall(req_text)))
    return prereqs, req_text


def _stub(sigle: str, name: str = "", credits: int = 0) -> dict:
    return {
        "id": sigle, "name": name, "credits": credits, "description": "",
        "prerequisite_courses": [], "concomitant_courses": [],
        "equivalent_courses": [], "requirement_text": "",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Tous les sigles du programme
    print(f"Fetching programme 7617 : {PROGRAM_URL}")
    sigles = fetch_program_sigles()
    print(f"  {len(sigles)} cours dans le programme.\n")

    # 2. Scraper chaque cours du périmètre
    program_courses: list[dict] = []
    for i, sigle in enumerate(sigles, 1):
        course = parse_course_page(sigle)
        program_courses.append(course)
        prereq_str = f" ← {course['prerequisite_courses']}" if course["prerequisite_courses"] else ""
        print(f"  [{i:2d}/{len(sigles)}] {sigle:10s}  {course['credits']} cr  "
              f"{(course['name'] or '(sans titre)')[:45]}{prereq_str}")
        time.sleep(0.25)

    # 3. Prérequis hors-périmètre
    program_ids = {c["id"] for c in program_courses}
    other_ids: set[str] = set()
    for c in program_courses:
        for dep in c["prerequisite_courses"] + c["concomitant_courses"]:
            if dep not in program_ids:
                other_ids.add(dep)

    print(f"\n{len(other_ids)} cours hors-périmètre référencés comme prérequis.")
    other_courses: list[dict] = []
    for i, sigle in enumerate(sorted(other_ids), 1):
        course = parse_course_page(sigle)
        other_courses.append(course)
        print(f"  [{i:2d}/{len(other_ids)}] {sigle:10s}  {course['credits']} cr  "
              f"{course['name'][:45] or '(404 stub)'}")
        time.sleep(0.25)

    # 4. Sauvegarder
    result = {
        "metadata": {
            "source":        "UQAM – Baccalauréat en informatique (programme 7617)",
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

    subjects = sorted({SIGLE_RE.match(c["id"]).group(1)
                       for c in program_courses if SIGLE_RE.match(c["id"])})
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  PROGRAM : {len(program_courses)} cours  {subjects}")
    print(f"  OTHER   : {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
