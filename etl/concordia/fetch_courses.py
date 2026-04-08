"""
Scrape le calendrier académique de Concordia pour extraire les cours COMP.

Source : section 71.70.10 — Computer Science and Software Engineering Courses

Structure HTML réelle :
  <h3>COMP 228 System Hardware (3 credits)</h3>
  <div class="accordion-collapse collapse">
    <div class="accordion-body">
      <span class="requisites">...</span>   ← prérequis
      <p class="crse-descr">...</p>         ← description
    </div>
  </div>

Sauvegarde dans etl/concordia/raw_courses.json (même schéma que etl/udem/raw_courses.json).
"""

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

COURSES_URL = (
    "https://www.concordia.ca/academics/undergraduate/calendar/current"
    "/section-71-gina-cody-school-of-engineering-and-computer-science"
    "/section-71-70-department-of-computer-science-and-software-engineering"
    "/section-71-70-10-computer-science-and-software-engineering-courses.html"
)

OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# "COMP 228 System Hardware (3 credits)"
HEADER_RE = re.compile(
    r"^(COMP\s+\d{3}[A-Z0-9]*)\s+(.+?)\s+\((\d+(?:\.\d+)?)\s+credits?\)",
    re.IGNORECASE,
)


def parse_requisites(requisites_span) -> tuple[list[str], list[str], str]:
    """
    Extrait prerequisite_courses, concomitant_courses et requirement_text
    depuis <span class="requisites">.

    Le texte d'un même <p> peut mélanger les deux sections :
      "The following course must be completed previously: COMP 248.
       The following courses must be completed previously or concurrently: MATH 203 or MATH 204."

    On parcourt les nœuds enfants pour savoir dans quelle section se trouve
    chaque lien de cours.
    """
    if requisites_span is None:
        return [], [], ""

    full_text = requisites_span.get_text(" ", strip=True)

    prereqs: list[str] = []
    coreqs:  list[str] = []

    for p in requisites_span.find_all("p"):
        # Mode courant : "prereq" ou "coreq"
        mode = "prereq"

        for node in p.children:
            # Nœud texte : met à jour le mode selon le contenu
            if isinstance(node, str):
                lower = node.lower()
                if "previously or concurrently" in lower:
                    mode = "coreq"
                elif "previously" in lower:
                    mode = "prereq"
                continue

            # Nœud tag : cherche un lien de cours
            if not hasattr(node, "find_all"):
                continue
            for a in node.find_all("a"):
                code_text = a.get_text(strip=True)
                if re.match(r"[A-Z]{2,5}\s+\d{3}", code_text):
                    if mode == "coreq":
                        coreqs.append(code_text)
                    else:
                        prereqs.append(code_text)

    return (
        list(dict.fromkeys(prereqs)),
        list(dict.fromkeys(coreqs)),
        full_text,
    )


def parse_courses(soup: BeautifulSoup) -> list[dict]:
    courses = []

    for h3 in soup.find_all("h3"):
        text = h3.get_text(" ", strip=True)
        m = HEADER_RE.match(text)
        if not m:
            continue

        course_id = re.sub(r"\s+", " ", m.group(1).upper().strip())
        title     = m.group(2).strip()
        credits   = float(m.group(3))

        # Le contenu est dans le premier <div class="accordion-collapse"> suivant
        accordion = h3.find_next_sibling("div", class_="accordion-collapse")
        if accordion is None:
            courses.append({
                "id": course_id, "name": title, "credits": credits,
                "description": "", "prerequisite_courses": [],
                "concomitant_courses": [], "equivalent_courses": [],
                "requirement_text": "",
            })
            continue

        # Description : <p class="crse-descr">
        desc_p = accordion.find("p", class_="crse-descr")
        description = ""
        if desc_p:
            # Retire le <h4>Description:</h4> du texte
            for h4 in desc_p.find_all("h4"):
                h4.decompose()
            description = desc_p.get_text(" ", strip=True)

        # Prérequis : <span class="requisites">
        requisites_span = accordion.find("span", class_="requisites")
        prereqs, coreqs, req_text = parse_requisites(requisites_span)

        courses.append({
            "id":                   course_id,
            "name":                 title,
            "credits":              credits,
            "description":          description,
            "prerequisite_courses": prereqs,
            "concomitant_courses":  coreqs,
            "equivalent_courses":   [],
            "requirement_text":     req_text,
        })

    return courses


def main():
    print(f"Fetching {COURSES_URL} ...")
    resp = requests.get(COURSES_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    courses = parse_courses(soup)

    with_prereqs = [c for c in courses if c["prerequisite_courses"]]

    result = {
        "metadata": {
            "source":     "Concordia University – Undergraduate Calendar (current)",
            "url":        COURSES_URL,
            "comp_count": len(courses),
        },
        "courses": {
            "COMP": courses,
        },
    }

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Sauvegardé {len(courses)} cours COMP dans {OUTPUT_FILE}")
    print(f"  Avec prérequis: {len(with_prereqs)}")
    print()
    for c in courses[:6]:
        print(f"  {c['id']:10s} {c['credits']:3g} cr  {c['name']}")
        if c["prerequisite_courses"]:
            print(f"             Prérequis:  {c['prerequisite_courses']}")
        if c["concomitant_courses"]:
            print(f"             Corequis:   {c['concomitant_courses']}")


if __name__ == "__main__":
    main()
