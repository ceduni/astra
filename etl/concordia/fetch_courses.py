"""
Scrape le programme BCompSc in Computer Science de Concordia (90 crédits).

Sources :
  • Page programme (section-71-70-2) → périmètre exact de tous les cours nommés
    (Core, Complementary Core, AI/Games/Data/Web groups, Math Electives, CS Electives)
  • section-71-70-10 → détails (description, prérequis, corequis) pour COMP et SOEN
  • section-71-60   → détails pour les cours ENCS
  • Pool ouvert : tous les COMP ≥ 325 de section-71-70-10
    (règle "CS Electives : all COMP courses with numbers 325 or higher")

Périmètre (hors_perimetre: false) = cours explicitement listés dans le programme
  + tous les COMP ≥ 325

Sauvegarde dans etl/concordia/raw_courses.json.
"""

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.concordia.ca/academics/undergraduate/calendar/current"

PROGRAM_URL  = (
    f"{BASE}/section-71-gina-cody-school-of-engineering-and-computer-science"
    "/section-71-70-department-of-computer-science-and-software-engineering"
    "/section-71-70-2-degree-requirements-bcompsc-.html"
)
COMP_SOEN_URL = (
    f"{BASE}/section-71-gina-cody-school-of-engineering-and-computer-science"
    "/section-71-70-department-of-computer-science-and-software-engineering"
    "/section-71-70-10-computer-science-and-software-engineering-courses.html"
)
ENCS_URL = (
    f"{BASE}/section-71-gina-cody-school-of-engineering-and-computer-science"
    "/section-71-60-engineering-course-descriptions"
    "/engineering-and-computer-science-courses.html"
)

OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Sections à ne pas inclure dans le périmètre
SKIP_SECTIONS = {
    "BCompSc in Computer Science (90 credits)",  # tableau résumé
    "General Electives: BCompSc (27 credits)",   # pool trop large (tout l'université)
    "General Electives Exclusion List",           # cours explicitement exclus
    "Other Related Programs",
    "Degree Requirements",
    "Computer Science Elective Course Groups",    # en-tête parent seulement
}


# ── Page programme ────────────────────────────────────────────────────────────

def fetch_explicit_program_courses(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Extrait tous les cours listés dans le programme (div.formatted-course),
    sauf ceux dans les sections à ignorer.
    Retourne {sigle: {name, credits}}.
    """
    current_section = ""
    skip = False
    result: dict[str, dict] = {}

    for el in soup.descendants:
        if not hasattr(el, "name") or el.name is None:
            continue
        if el.name in ("h2", "h3"):
            current_section = el.get_text(strip=True)
            skip = current_section in SKIP_SECTIONS
            continue
        if skip:
            continue
        if el.name == "div" and "formatted-course" in el.get("class", []):
            code_el  = el.find("span", class_="course-code-number")
            title_el = el.find("span", class_="course-title")
            cred_el  = el.find("span", class_="course-credits")
            if not code_el:
                continue
            sigle = re.sub(r"\s+", " ", code_el.get_text(strip=True))
            if sigle not in result:
                result[sigle] = {
                    "name":    title_el.get_text(strip=True) if title_el else "",
                    "credits": float(cred_el.get_text(strip=True)) if cred_el else 0.0,
                }
    return result


# ── Pages de cours (accordion) ────────────────────────────────────────────────

HEADER_RE = re.compile(
    r"^([A-Z]{2,5})\s+(\d{3,4}[A-Z0-9]*)\s+(.+?)\s+\(([\d.]+)\s+credits?\)",
    re.IGNORECASE,
)


def _walk_nodes_for_requisites(nodes) -> tuple[list[str], list[str]]:
    """
    Parcourt une séquence de nœuds enfants et extrait les codes de cours
    selon le mode (prereq / coreq) déduit des nœuds texte.
    """
    prereqs: list[str] = []
    coreqs:  list[str] = []
    mode = "prereq"

    for node in nodes:
        if isinstance(node, str):
            lower = node.lower()
            if "previously or concurrently" in lower:
                mode = "coreq"
            elif "previously" in lower:
                mode = "prereq"
            continue
        if not hasattr(node, "find_all"):
            continue
        for a in node.find_all("a"):
            code_text = re.sub(r"\s+", " ", a.get_text(strip=True))
            if re.match(r"[A-Z]{2,5}\s+\d{3}", code_text):
                (coreqs if mode == "coreq" else prereqs).append(code_text)

    return prereqs, coreqs


def parse_requisites(requisites_span) -> tuple[list[str], list[str], str]:
    if requisites_span is None:
        return [], [], ""

    full_text = requisites_span.get_text(" ", strip=True)
    prereqs: list[str] = []
    coreqs:  list[str] = []

    p_tags = requisites_span.find_all("p")
    if p_tags:
        # Structure avec <p> : itérer par paragraphe
        for p in p_tags:
            pre, co = _walk_nodes_for_requisites(p.children)
            prereqs.extend(pre)
            coreqs.extend(co)
    else:
        # Structure plate : itérer directement les enfants du span
        pre, co = _walk_nodes_for_requisites(requisites_span.children)
        prereqs.extend(pre)
        coreqs.extend(co)

    return (
        list(dict.fromkeys(prereqs)),
        list(dict.fromkeys(coreqs)),
        full_text,
    )


def parse_accordion_courses(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Parse une page de cours en accordéon (h3 + accordion-collapse).
    Retourne {sigle: full_course_dict}.
    """
    result: dict[str, dict] = {}

    for h3 in soup.find_all("h3"):
        text = h3.get_text(" ", strip=True)
        m = HEADER_RE.match(text)
        if not m:
            continue

        subj    = m.group(1).upper()
        num     = m.group(2).upper()
        sigle   = f"{subj} {num}"
        title   = m.group(3).strip()
        credits = float(m.group(4))

        accordion = h3.find_next_sibling("div", class_="accordion-collapse")
        if accordion is None:
            result[sigle] = _course_stub(sigle, title, credits)
            continue

        desc_p = accordion.find("p", class_="crse-descr")
        description = ""
        if desc_p:
            for h4 in desc_p.find_all("h4"):
                h4.decompose()
            description = desc_p.get_text(" ", strip=True)

        req_span = accordion.find("span", class_="requisites")
        prereqs, coreqs, req_text = parse_requisites(req_span)

        result[sigle] = {
            "id":                   sigle,
            "name":                 title,
            "credits":              credits,
            "description":          description,
            "prerequisite_courses": prereqs,
            "concomitant_courses":  coreqs,
            "equivalent_courses":   [],
            "requirement_text":     req_text,
        }

    return result


def _course_stub(sigle: str, name: str = "", credits: float = 0.0) -> dict:
    return {
        "id": sigle, "name": name, "credits": credits, "description": "",
        "prerequisite_courses": [], "concomitant_courses": [],
        "equivalent_courses": [], "requirement_text": "",
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Page programme : cours explicitement nommés
    print(f"Fetching programme page…")
    prog_resp = SESSION.get(PROGRAM_URL, timeout=30)
    prog_resp.raise_for_status()
    prog_resp.encoding = "utf-8"
    prog_soup = BeautifulSoup(prog_resp.text, "html.parser")

    explicit = fetch_explicit_program_courses(prog_soup)
    print(f"  {len(explicit)} cours dans les tables du programme.")

    # 2. Détails COMP + SOEN depuis section-71-70-10
    print(f"\nFetching COMP/SOEN course details…")
    cs_resp = SESSION.get(COMP_SOEN_URL, timeout=30)
    cs_resp.raise_for_status()
    cs_resp.encoding = "utf-8"
    cs_soup = BeautifulSoup(cs_resp.text, "html.parser")
    cs_details = parse_accordion_courses(cs_soup)
    print(f"  {len(cs_details)} cours COMP/SOEN trouvés.")

    # 3. Détails ENCS depuis section-71-60
    print(f"\nFetching ENCS course details…")
    encs_resp = SESSION.get(ENCS_URL, timeout=30)
    encs_resp.raise_for_status()
    encs_resp.encoding = "utf-8"
    encs_soup = BeautifulSoup(encs_resp.text, "html.parser")
    encs_details = parse_accordion_courses(encs_soup)
    print(f"  {len(encs_details)} cours ENCS trouvés.")

    all_details = {**cs_details, **encs_details}

    # 4. Pool ouvert COMP ≥ 325 (règle CS Electives)
    comp_325_plus = {
        sigle: data
        for sigle, data in cs_details.items()
        if sigle.startswith("COMP ")
        and int(re.search(r"\d+", sigle.split()[1]).group()) >= 325
    }
    print(f"\n  {len(comp_325_plus)} cours COMP ≥ 325 (pool ouvert CS Electives).")

    # 5. Périmètre final = explicites ∪ COMP ≥ 325
    in_scope_sigles: set[str] = set(explicit.keys()) | set(comp_325_plus.keys())

    # Construire les dicts complets pour chaque cours du périmètre
    program_courses: list[dict] = []
    for sigle in sorted(in_scope_sigles):
        if sigle in all_details:
            program_courses.append(all_details[sigle])
        else:
            # Cours hors section-71-70-10/71-60 (MAST, MATH, ENGR…) :
            # on utilise le nom/crédits de la page programme
            prog_info = explicit.get(sigle, {})
            program_courses.append(_course_stub(
                sigle,
                name=prog_info.get("name", ""),
                credits=prog_info.get("credits", 0.0),
            ))

    # 6. Prérequis hors périmètre
    other_sigles: set[str] = set()
    for c in program_courses:
        for dep in c["prerequisite_courses"] + c["concomitant_courses"]:
            if dep not in in_scope_sigles:
                other_sigles.add(dep)

    other_courses: list[dict] = []
    for sigle in sorted(other_sigles):
        if sigle in all_details:
            other_courses.append(all_details[sigle])
        else:
            other_courses.append(_course_stub(sigle))

    # 7. Sauvegarder
    result = {
        "metadata": {
            "source":        "Concordia – BCompSc in Computer Science (90 credits)",
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

    subjects = sorted({c["id"].split()[0] for c in program_courses})
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  PROGRAM : {len(program_courses)} cours  {subjects}")
    print(f"  OTHER   : {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
