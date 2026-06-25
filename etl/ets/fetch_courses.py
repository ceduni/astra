"""
Scrape le site web de l'ÉTS pour deux programmes :
  - Baccalauréat en génie logiciel
  - Baccalauréat en informatique distribuée

Stratégie :
  1. Page programme → JSON coursesBlock embarqué → IDs numériques (dédoublonnés)
  2. api/courses/get?ids=... → sigle + titre + crédits pour chaque ID
  3. /etudes/cours/{sigle} → description, prérequis, concomitants, requirement_text
  4. Prérequis référencés hors des deux périmètres → hors_perimetre: true

Sauvegarde dans etl/ets/raw_courses.json.
"""

import json
import re
import time
from html import unescape
from pathlib import Path
from typing import Optional

import requests

BASE_URL    = "https://www.etsmtl.ca"
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

PROGRAMS = [
    {
        "name": "Baccalauréat en génie logiciel",
        "url":  f"{BASE_URL}/programmes-formations/baccalaureat-genie-logiciel",
    },
    {
        "name": "Baccalauréat en informatique distribuée",
        "url":  f"{BASE_URL}/programmes-formations/baccalaureat-informatique-distribuee",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "fr-CA,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Matches ETS course codes: 2-4 uppercase letters + 3 digits + optional letter/digit
_SIGLE_RE = re.compile(r"\b([A-Z]{2,4}\d{3}[A-Z]?\d?)\b")


# ── Programme discovery ────────────────────────────────────────────────────────

def extract_program_ids(program_url: str) -> list[str]:
    """
    Fetch the program page and return the ordered, deduplicated list of
    numeric course IDs embedded in the coursesBlock JSON.
    """
    resp = SESSION.get(program_url, timeout=30)
    resp.raise_for_status()
    html = resp.text

    idx = html.find("coursesBlock")
    if idx < 0:
        raise RuntimeError(f"coursesBlock not found on {program_url}")

    raw = unescape(html[idx: idx + 60000])
    ids = list(dict.fromkeys(re.findall(r'"course_id":(\d+)', raw)))
    return ids


def resolve_ids(ids: list[str]) -> list[dict]:
    """
    Call api/courses/get with a comma-separated list of numeric IDs.
    Returns [{id, code, title, credits, url}, ...].
    """
    resp = SESSION.get(
        f"{BASE_URL}/api/courses/get",
        params={"ids": ",".join(ids)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── Course page scraping ───────────────────────────────────────────────────────

def _boxed_info(html: str) -> dict[str, str]:
    """
    Parse all o-boxed-info__item sections and return a {label: raw_text} dict.
    raw_text still contains HTML tags for li-based values.
    """
    pairs = re.findall(
        r"o-boxed-info__title[^>]*>(.*?)</div>.*?o-boxed-info__text[^>]*>(.*?)</div>",
        html,
        re.DOTALL,
    )
    result = {}
    for title_html, text_html in pairs:
        label = re.sub(r"<[^>]+>", "", title_html).strip()
        result[label] = text_html
    return result


def _strip(html_fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def scrape_course(sigle: str) -> Optional[dict]:
    """
    Scrape /etudes/cours/{sigle} and return a raw course dict, or None on 404.
    """
    url = f"{BASE_URL}/etudes/cours/{sigle.lower()}"
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗ {sigle}: {e}")
        return None

    html = resp.text

    # ── Title ────────────────────────────────────────────────────────────────
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    name = ""
    if h1_m:
        raw = unescape(re.sub(r"<[^>]+>", "", h1_m.group(1))).replace("\xa0", " ").strip()
        # Format: "GTI525 - Technologies de développement Internet"
        if " - " in raw:
            name = raw.split(" - ", 1)[1].strip()

    # ── Meta description ─────────────────────────────────────────────────────
    meta_m = re.search(r'<meta name="description" content="(.*?)"', html)
    description = unescape(meta_m.group(1)) if meta_m else ""

    # ── Sidebar fields ───────────────────────────────────────────────────────
    info = _boxed_info(html)

    credits_raw = _strip(info.get("Crédits", "0"))
    try:
        credits = int(credits_raw.split()[0])
    except (ValueError, IndexError):
        credits = 0

    prereqs_text = _strip(info.get("Préalable(s)", ""))
    prereqs = _SIGLE_RE.findall(prereqs_text)

    # ── Body paragraphs ──────────────────────────────────────────────────────
    paragraphs = []
    for p_html in re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
        text = _strip(p_html)
        if len(text) > 15:
            paragraphs.append(text)

    # requirement_text: paragraphs that mention prereqs or corequisites,
    # used by parse_prereqs() for OR/AND connector detection.
    req_parts = [
        t for t in paragraphs
        if re.search(r"[Pp]r[eé]alable|[Cc]oncomitant", t)
    ]
    requirement_text = " | ".join(req_parts)

    # Corequisites: extract sigles from "concomitant" paragraphs.
    concomitants: list[str] = []
    seen_conc: set[str] = set()
    for t in paragraphs:
        if "concomitant" in t.lower():
            for m in _SIGLE_RE.finditer(t):
                code = m.group(1)
                if code != sigle.upper() and code not in seen_conc:
                    seen_conc.add(code)
                    concomitants.append(code)

    return {
        "id":                   sigle.upper(),
        "name":                 name,
        "credits":              credits,
        "description":          description,
        "prerequisite_courses": prereqs,
        "concomitant_courses":  concomitants,
        "equivalent_courses":   [],
        "requirement_text":     requirement_text,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Discover course codes for both programs
    all_program_codes: dict[str, dict] = {}  # sigle → {name, credits, ...}

    for prog in PROGRAMS:
        print(f"\nFetching programme : {prog['name']}")
        ids = extract_program_ids(prog["url"])
        print(f"  {len(ids)} IDs extraits de la page.")

        courses_meta = resolve_ids(ids)
        print(f"  {len(courses_meta)} cours résolus via api/courses/get.")

        for c in courses_meta:
            code = c["code"].upper()
            if code not in all_program_codes:
                all_program_codes[code] = c

    print(f"\nTotal cours périmètre (union des 2 programmes) : {len(all_program_codes)}")

    # 2. Scrape each program course
    program_courses: list[dict] = []
    codes_sorted = sorted(all_program_codes)
    for i, sigle in enumerate(codes_sorted, 1):
        course = scrape_course(sigle)
        if course:
            program_courses.append(course)
            print(f"  [{i:3d}/{len(codes_sorted)}] ✓ {sigle} — {course['name'][:55]}")
        else:
            print(f"  [{i:3d}/{len(codes_sorted)}] ✗ {sigle} (404)")
        time.sleep(0.25)

    # 3. Prereqs referenced outside the program scope
    program_id_set = {c["id"] for c in program_courses}
    other_ids: set[str] = set()
    for c in program_courses:
        for dep in c["prerequisite_courses"] + c["concomitant_courses"]:
            if dep not in program_id_set:
                other_ids.add(dep)

    print(f"\n{len(other_ids)} cours hors-périmètre référencés comme prérequis.")
    other_courses: list[dict] = []
    for i, sigle in enumerate(sorted(other_ids), 1):
        course = scrape_course(sigle)
        if course:
            other_courses.append(course)
            print(f"  [{i:2d}/{len(other_ids)}] ✓ {sigle} — {course['name'][:55]}")
        else:
            other_courses.append({
                "id": sigle, "name": "", "credits": 0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            })
            print(f"  [{i:2d}/{len(other_ids)}] ✗ {sigle} (404 — stub)")
        time.sleep(0.25)

    # 4. Save
    subjects = sorted({c["id"][:3] for c in program_courses})
    result = {
        "metadata": {
            "source":        "ÉTS — site web etsmtla.ca",
            "programs":      [p["name"] for p in PROGRAMS],
            "program_count": len(program_courses),
            "other_count":   len(other_courses),
            "subjects":      subjects,
        },
        "courses": {
            "PROGRAM": program_courses,
            "OTHER":   other_courses,
        },
    }

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  PROGRAM : {len(program_courses)} cours  {subjects}")
    print(f"  OTHER   : {len(other_courses)} cours hors-périmètre")


if __name__ == "__main__":
    main()
