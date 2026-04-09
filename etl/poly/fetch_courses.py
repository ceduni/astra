"""
Scrape les deux programmes de Polytechnique Montréal :
  • Génie informatique  (bc-informatique)
  • Génie logiciel      (bc-logiciel)

Stratégie :
  1. Pour chaque page programme → parser table.tableau-cours :
       tr.titre  → sigle, titre, crédits
       tr.contenu → préalables (liens <a>) et corequis
  2. Union des deux périmètres ; un cours dans les deux programmes
     n'est compté qu'une fois (hors_perimetre: false).
  3. Pour chaque cours du périmètre → GET /programmes/cours/{slug}
     → description (div.desc), préalables précis (div.details).
  4. Prérequis référencés hors périmètre → hors_perimetre: true.

Sauvegarde dans etl/poly/raw_courses.json.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL  = "https://www.polymtl.ca"
PROGRAMS  = {
    "bc-informatique": "Génie informatique",
    "bc-logiciel":     "Génie logiciel",
}
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

SIGLE_RE = re.compile(r"^[A-Z]{2,4}\d{4}[A-Z]?$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url: str) -> BeautifulSoup:
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _extract_prereq_links(div) -> list[str]:
    """Extrait les sigles depuis les liens <a> dans un bloc div.details."""
    sigles: list[str] = []
    if div is None:
        return sigles
    for a in div.find_all("a"):
        text = a.get_text(strip=True).upper()
        if SIGLE_RE.match(text):
            sigles.append(text)
    return list(dict.fromkeys(sigles))


# ── Page programme ────────────────────────────────────────────────────────────

def parse_program_page(slug: str) -> dict[str, dict]:
    """
    Parse une page programme Poly et retourne un dict {sigle: course_stub}
    avec les champs id, name, credits, prerequisite_courses, concomitant_courses,
    et _slug (pour fetch de la page individuelle).
    """
    url  = f"{BASE_URL}/programmes/programmes/{slug}"
    soup = _get(url)
    print(f"  Parsing {url}")

    courses: dict[str, dict] = {}
    current_titre_sigle: Optional[str] = None

    for tr in soup.select("table.tableau-cours tr"):
        if "titre" in tr.get("class", []):
            # Ligne de cours : sigle, titre, crédits
            td_sigle   = tr.find("td", class_="sigle")
            td_titre   = tr.find("td", class_="titre")
            td_credits = tr.find("td", class_="credits")
            if not td_sigle:
                current_titre_sigle = None
                continue

            raw_sigle = td_sigle.get_text(strip=True).upper()
            # Le td.sigle peut contenir un lien ou juste du texte
            a_tag = td_sigle.find("a")
            href  = a_tag["href"] if a_tag and a_tag.get("href") else None
            course_slug = href.rstrip("/").split("/")[-1] if href else None

            if not SIGLE_RE.match(raw_sigle):
                current_titre_sigle = None
                continue

            current_titre_sigle = raw_sigle
            if raw_sigle not in courses:
                credits_text = td_credits.get_text(strip=True) if td_credits else "0"
                try:
                    credits = float(credits_text)
                except ValueError:
                    credits = 0.0

                courses[raw_sigle] = {
                    "id":                   raw_sigle,
                    "name":                 td_titre.get_text(strip=True) if td_titre else "",
                    "credits":              credits,
                    "description":          "",
                    "prerequisite_courses": [],
                    "concomitant_courses":  [],
                    "equivalent_courses":   [],
                    "requirement_text":     "",
                    "_slug":                course_slug,
                }

        elif "contenu" in tr.get("class", []) and current_titre_sigle:
            # Ligne de détails : préalables et corequis
            details_div = tr.find("div", class_="details")
            if not details_div:
                continue

            prereqs: list[str] = []
            coreqs:  list[str] = []
            req_parts: list[str] = []

            # Chercher les sections "Préalable(s)" et "Corequis"
            current_mode = None
            for child in details_div.children:
                if not hasattr(child, "name"):
                    text = str(child).strip()
                    if not text:
                        continue
                    lower = text.lower()
                    if "préalable" in lower:
                        current_mode = "prereq"
                    elif "corequis" in lower:
                        current_mode = "coreq"
                    elif current_mode and text:
                        req_parts.append(text)
                    continue

                if child.name == "a":
                    code = child.get_text(strip=True).upper()
                    if SIGLE_RE.match(code):
                        if current_mode == "prereq":
                            prereqs.append(code)
                        elif current_mode == "coreq":
                            coreqs.append(code)

            req_text = " ".join(req_parts).strip()
            c = courses[current_titre_sigle]
            c["prerequisite_courses"] = list(dict.fromkeys(prereqs))
            c["concomitant_courses"]  = list(dict.fromkeys(coreqs))
            if req_text:
                c["requirement_text"] = req_text

    return courses


# ── Page individuelle ─────────────────────────────────────────────────────────

def fetch_course_detail(sigle: str, slug: Optional[str]) -> Optional[dict]:
    """
    Récupère la description depuis la page individuelle du cours.
    Retourne None si le slug est inconnu ou la page introuvable.
    """
    if not slug:
        return None
    url = f"{BASE_URL}/programmes/cours/{slug}"
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = _get.__wrapped__(url) if hasattr(_get, "__wrapped__") else None
    # Re-parse from already-fetched response
    soup = BeautifulSoup(resp.text, "html.parser")

    node = soup.find("div", class_="node--cours")
    if node is None:
        return None

    # Description
    desc_div = node.find("div", class_="desc")
    description = desc_div.get_text(" ", strip=True) if desc_div else ""

    # Credits — try common Drupal field patterns then fall back to regex in full text
    credits: float = 0.0
    credit_el = (
        node.find(class_=re.compile(r"credit", re.I))
        or node.find("div", class_="credits")
    )
    if credit_el:
        m = re.search(r"(\d+(?:[.,]\d+)?)", credit_el.get_text())
        if m:
            credits = float(m.group(1).replace(",", "."))
    if credits == 0.0:
        # fallback: scan the full node text for "X crédit(s)" (cap at 15 to avoid degree totals)
        m = re.search(r"\b(\d{1,2}(?:[.,]\d)?)\s*cr[ée]dit", node.get_text(), re.I)
        if m:
            v = float(m.group(1).replace(",", "."))
            if v <= 15:
                credits = v

    # Préalables et corequis depuis div.details de la page individuelle
    details_div = node.find("div", class_="details")
    prereqs: list[str] = []
    coreqs:  list[str] = []
    req_text = ""

    if details_div:
        current_mode = None
        req_parts: list[str] = []
        for child in details_div.descendants:
            if isinstance(child, str):
                text = child.strip()
                if not text:
                    continue
                lower = text.lower()
                if "préalable" in lower:
                    current_mode = "prereq"
                elif "corequis" in lower:
                    current_mode = "coreq"
                elif current_mode:
                    req_parts.append(text)
            elif hasattr(child, "name") and child.name == "a":
                code = child.get_text(strip=True).upper()
                if SIGLE_RE.match(code):
                    if current_mode == "prereq":
                        prereqs.append(code)
                    elif current_mode == "coreq":
                        coreqs.append(code)
        req_text = " ".join(req_parts).strip()

    return {
        "description":          description,
        "credits":              credits,
        "prerequisite_courses": list(dict.fromkeys(prereqs)),
        "concomitant_courses":  list(dict.fromkeys(coreqs)),
        "requirement_text":     req_text,
    }


# ── Slug discovery ────────────────────────────────────────────────────────────

def discover_slug_from_prereq_links(soup: BeautifulSoup) -> dict[str, str]:
    """
    Parcourt tous les liens <a href="/programmes/cours/..."> de la page programme
    et retourne un dict {SIGLE: slug}.
    """
    mapping: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/programmes/cours/" not in href:
            continue
        slug  = href.rstrip("/").split("/")[-1]
        text  = a.get_text(strip=True).upper()
        if SIGLE_RE.match(text):
            mapping.setdefault(text, slug)
    return mapping


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    all_program: dict[str, dict] = {}   # sigle → course dict (union des deux programmes)
    slug_map:    dict[str, str]  = {}   # sigle → slug (pour les pages individuelles)

    # 1. Parser les deux pages programme
    for prog_slug, prog_name in PROGRAMS.items():
        print(f"\nFetching programme {prog_name} ({prog_slug})…")
        url  = f"{BASE_URL}/programmes/programmes/{prog_slug}"
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Collecter les slugs depuis tous les liens de la page
        slug_map.update(discover_slug_from_prereq_links(soup))

        # Parser table.tableau-cours directement depuis la soupe déjà chargée
        courses_this_prog: dict[str, dict] = {}
        current_titre_sigle: Optional[str] = None

        for tr in soup.select("table.tableau-cours tr"):
            classes = tr.get("class", [])

            if "titre" in classes:
                td_sigle   = tr.find("td", class_="sigle")
                td_titre   = tr.find("td", class_="titre")
                td_credits = tr.find("td", class_="credits")
                if not td_sigle:
                    current_titre_sigle = None
                    continue

                raw_sigle = td_sigle.get_text(strip=True).upper()
                a_tag = td_sigle.find("a")
                if a_tag and a_tag.get("href"):
                    href = a_tag["href"]
                    slug_map.setdefault(raw_sigle, href.rstrip("/").split("/")[-1])

                if not SIGLE_RE.match(raw_sigle):
                    current_titre_sigle = None
                    continue

                current_titre_sigle = raw_sigle
                if raw_sigle not in courses_this_prog:
                    credits_text = td_credits.get_text(strip=True) if td_credits else "0"
                    try:
                        credits = float(credits_text)
                    except ValueError:
                        credits = 0.0

                    courses_this_prog[raw_sigle] = {
                        "id":                   raw_sigle,
                        "name":                 td_titre.get_text(strip=True) if td_titre else "",
                        "credits":              credits,
                        "description":          "",
                        "prerequisite_courses": [],
                        "concomitant_courses":  [],
                        "equivalent_courses":   [],
                        "requirement_text":     "",
                    }

            elif "contenu" in classes and current_titre_sigle:
                details_div = tr.find("div", class_="details")
                if not details_div:
                    continue

                prereqs: list[str] = []
                coreqs:  list[str] = []
                current_mode = None

                for child in details_div.children:
                    if child.name is None:  # NavigableString
                        text = str(child).strip()
                        if not text:
                            continue
                        lower = text.lower()
                        if "préalable" in lower:
                            current_mode = "prereq"
                        elif "corequis" in lower:
                            current_mode = "coreq"
                        continue
                    if child.name == "a":
                        code = child.get_text(strip=True).upper()
                        if SIGLE_RE.match(code):
                            if current_mode == "prereq":
                                prereqs.append(code)
                            elif current_mode == "coreq":
                                coreqs.append(code)
                    else:
                        # nested spans/divs
                        for a in child.find_all("a"):
                            code = a.get_text(strip=True).upper()
                            if SIGLE_RE.match(code):
                                if current_mode == "prereq" and code not in prereqs:
                                    prereqs.append(code)
                                elif current_mode == "coreq" and code not in coreqs:
                                    coreqs.append(code)

                c = courses_this_prog[current_titre_sigle]
                c["prerequisite_courses"] = list(dict.fromkeys(prereqs))
                c["concomitant_courses"]  = list(dict.fromkeys(coreqs))

        print(f"  {len(courses_this_prog)} cours trouvés dans {prog_name}.")

        # Union : cours dans les deux programmes compté une fois
        for sigle, course in courses_this_prog.items():
            if sigle not in all_program:
                all_program[sigle] = course

    program_ids = set(all_program.keys())
    print(f"\nTotal unique programme : {len(all_program)} cours.")

    # 2. Enrichir avec les pages individuelles (description)
    print("\nFetch des pages individuelles pour les descriptions…")
    for i, (sigle, course) in enumerate(all_program.items(), 1):
        slug = slug_map.get(sigle)
        if not slug:
            print(f"  [{i:3d}/{len(all_program)}] {sigle:10s}  (pas de slug, skip)")
            continue

        detail = fetch_course_detail(sigle, slug)
        if detail:
            course["description"] = detail["description"]
            if detail.get("credits", 0.0) > 0:
                course["credits"] = detail["credits"]
            # Préférer les préalables de la page individuelle si plus complets
            if detail["prerequisite_courses"]:
                course["prerequisite_courses"] = detail["prerequisite_courses"]
            if detail["concomitant_courses"]:
                course["concomitant_courses"] = detail["concomitant_courses"]
            if detail["requirement_text"]:
                course["requirement_text"] = detail["requirement_text"]

        prereq_str = f" ← {course['prerequisite_courses']}" if course["prerequisite_courses"] else ""
        print(f"  [{i:3d}/{len(all_program)}] {sigle:10s}  {course['credits']:.0f} cr  "
              f"{(course['name'] or '(sans titre)')[:45]}{prereq_str}")
        time.sleep(0.2)

    # 3. Prérequis hors périmètre
    other_ids: set[str] = set()
    for c in all_program.values():
        for dep in c["prerequisite_courses"] + c["concomitant_courses"]:
            if dep not in program_ids:
                other_ids.add(dep)

    print(f"\n{len(other_ids)} cours hors-périmètre référencés comme prérequis.")
    other_courses: list[dict] = []
    for sigle in sorted(other_ids):
        slug   = slug_map.get(sigle)
        detail = fetch_course_detail(sigle, slug) if slug else None
        if detail:
            other_courses.append({
                "id":                   sigle,
                "name":                 "",
                "credits":              detail.get("credits", 0.0),
                "description":          detail["description"],
                "prerequisite_courses": detail["prerequisite_courses"],
                "concomitant_courses":  detail["concomitant_courses"],
                "equivalent_courses":   [],
                "requirement_text":     detail["requirement_text"],
            })
        else:
            other_courses.append({
                "id": sigle, "name": "", "credits": 0.0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            })
        print(f"  {sigle}")
        time.sleep(0.2)

    # 4. Sauvegarder
    program_courses = list(all_program.values())
    result = {
        "metadata": {
            "source":        "Polytechnique Montréal – Génie informatique & Génie logiciel",
            "programs":      list(PROGRAMS.keys()),
            "program_count": len(program_courses),
            "other_count":   len(other_courses),
        },
        "courses": {
            "PROGRAM": program_courses,
            "OTHER":   other_courses,
        },
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    subjects = sorted({c["id"][:3] for c in program_courses})
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  PROGRAM : {len(program_courses)} cours  {subjects}")
    print(f"  OTHER   : {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
