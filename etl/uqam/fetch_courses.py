"""
Scrape le programme 7617 (Baccalauréat en informatique) de l'UQAM.

Note : malgré le contenu dynamique apparent sur la page programme (accordions
Bootstrap), les pages individuelles de cours sont entièrement server-side
rendered — requests + BeautifulSoup suffisent, Playwright n'est pas nécessaire.

Stratégie :
  1. Page programme → extraire tous les sigles (INF, MAT, INM, etc.)
  2. Pour chaque sigle → page individuelle → extraire titre, crédits,
     description, préalables académiques

Sauvegarde dans etl/uqam/raw_courses.json (même schéma que les autres ETLs).
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

# Sigle UQAM : 2-3 lettres + 4 chiffres + éventuellement suffixe (ex: INF1070, MAT1115)
SIGLE_RE      = re.compile(r"^([A-Z]{2,4})(\d{4}[A-Z0-9]*)$")
PREREQ_RE     = re.compile(r"\[([A-Z]{2,4}\d{4}[A-Z0-9]*)")


# ── Page programme ────────────────────────────────────────────────────────────

def fetch_program_sigles() -> list[str]:
    """Retourne tous les sigles listés dans le programme 7617."""
    resp = SESSION.get(PROGRAM_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    sigles = []
    for el in soup.select("div.ligne_cours[data-sigle]"):
        sigle = el["data-sigle"].strip()
        if SIGLE_RE.match(sigle):
            sigles.append(sigle)

    return list(dict.fromkeys(sigles))   # dédoublonnage ordre-stable


# ── Page individuelle ─────────────────────────────────────────────────────────

def parse_course_page(sigle: str) -> dict:
    """Fetch et parse la page d'un cours UQAM."""
    resp = SESSION.get(COURSE_URL.format(sigle=sigle), timeout=30)
    if resp.status_code == 404:
        return _empty(sigle)
    resp.raise_for_status()

    soup  = BeautifulSoup(resp.text, "html.parser")
    desc  = soup.find(id="description")

    if desc is None:
        return _empty(sigle)

    full_text = desc.get_text("\n", strip=True)
    lines     = [l.strip() for l in full_text.splitlines() if l.strip()]

    # Titre complet depuis <h1>
    h1 = soup.find("h1", class_="title")
    name = ""
    if h1:
        h1_text = h1.get_text(" ", strip=True)
        # "COURS // INF2050 - Outils et pratiques..." → "Outils et pratiques..."
        name = re.sub(r"^.*?//\s*[A-Za-z]{2,4}\d{4}\S*\s*-\s*", "", h1_text, flags=re.IGNORECASE).strip()

    # Crédits — "Nombre de crédits" sur une ligne, ": 3" sur la suivante
    credits = 0
    for i, line in enumerate(lines):
        if "Nombre de crédits" in line:
            # Valeur peut être sur la même ligne ou sur la suivante
            m = re.search(r":\s*(\d+)", line)
            if not m and i + 1 < len(lines):
                m = re.search(r":\s*(\d+)", lines[i + 1])
            if m:
                credits = int(m.group(1))
            break

    # Description = Objectifs + Sommaire du contenu
    description = _extract_section(lines, ["Objectifs", "Sommaire du contenu"])

    # Préalables académiques
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
    """
    Extrait le texte des sections nommées dans la liste de lignes.
    Arrête à la section suivante connue.
    """
    known_sections = {
        "Objectifs", "Sommaire du contenu", "Modalité d'enseignement",
        "Préalables académiques", "Concomitants", "Préalables cours",
        "Préalables autres", "Programmes associés à ce cours",
        "Cycle", "Type de cours", "Nombre de crédits", "Discipline",
    }
    collecting   = False
    parts: list[str] = []

    for line in lines:
        is_section_header = line in known_sections

        if line in section_names:
            collecting = True
            continue
        if is_section_header and collecting:
            # On a atteint une autre section, mais on continue si c'est
            # aussi une section qu'on veut
            if line in section_names:
                continue
            else:
                # Continuer si d'autres section_names restent à voir
                collecting = False
        if collecting and not is_section_header:
            parts.append(line)

    return " ".join(parts).strip()


def _extract_prereqs(lines: list[str]) -> tuple[list[str], str]:
    """
    Extrait les codes de préalables depuis la section 'Préalables académiques'.
    Format attendu : [INF1070 Utilisation et administration...]
    """
    in_section  = False
    req_lines: list[str] = []

    for line in lines:
        if line == "Préalables académiques":
            in_section = True
            continue
        if in_section:
            # Arrêt aux autres sections connues
            if line in {
                "Objectifs", "Sommaire du contenu", "Modalité d'enseignement",
                "Concomitants", "Préalables cours", "Préalables autres",
                "Programmes associés à ce cours",
            }:
                break
            req_lines.append(line)

    req_text = " ".join(req_lines).strip()
    prereqs  = list(dict.fromkeys(PREREQ_RE.findall(req_text)))
    return prereqs, req_text


def _empty(sigle: str) -> dict:
    return {
        "id": sigle, "name": "", "credits": 0, "description": "",
        "prerequisite_courses": [], "concomitant_courses": [],
        "equivalent_courses": [], "requirement_text": "",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Récupérer tous les sigles du programme
    print(f"Fetching programme 7617 : {PROGRAM_URL}")
    sigles = fetch_program_sigles()
    print(f"  {len(sigles)} cours trouvés dans le programme.\n")

    # 2. Scraper chaque cours
    inf_courses:   list[dict] = []
    other_courses: list[dict] = []

    for i, sigle in enumerate(sigles, 1):
        course = parse_course_page(sigle)
        subj   = SIGLE_RE.match(sigle).group(1) if SIGLE_RE.match(sigle) else ""

        if subj == "INF":
            inf_courses.append(course)
        else:
            other_courses.append(course)

        name_preview = course["name"][:45] or "(sans titre)"
        prereq_str   = f" ← {course['prerequisite_courses']}" if course["prerequisite_courses"] else ""
        print(f"  [{i:2d}/{len(sigles)}] {sigle:10s}  {course['credits']} cr  {name_preview}{prereq_str}")
        time.sleep(0.25)

    # 3. Sauvegarder
    result = {
        "metadata": {
            "source":      "UQAM – Baccalauréat en informatique (programme 7617)",
            "program_url": PROGRAM_URL,
            "inf_count":   len(inf_courses),
            "other_count": len(other_courses),
        },
        "courses": {
            "INF":   inf_courses,
            "OTHER": other_courses,
        },
    }

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  INF:   {len(inf_courses)} cours")
    print(f"  OTHER: {len(other_courses)} cours ({', '.join(sorted({SIGLE_RE.match(c['id']).group(1) for c in other_courses if SIGLE_RE.match(c['id'])}))})")


if __name__ == "__main__":
    main()
