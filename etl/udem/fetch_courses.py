"""
Fetch tous les cours IFT de l'UdeM (response_level=full),
identifie les prérequis MAT référencés, les fetch aussi,
et sauvegarde tout dans raw_courses.json.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://planifium-api.onrender.com/api/v1"
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"

SESSION = requests.Session()


def fetch_subject(subject: str) -> list[dict]:
    """Fetch tous les cours d'un sujet donné avec response_level=full."""
    courses = []
    offset = 0
    limit = 100

    while True:
        resp = SESSION.get(
            f"{BASE_URL}/courses",
            params={
                "subject": subject,
                "response_level": "full",
                "limit": limit,
                "offset": offset,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # L'API peut retourner une liste directement ou un objet paginé
        if isinstance(data, list):
            batch = data
        else:
            batch = data.get("courses", data.get("items", data.get("results", [])))

        if not batch:
            break

        courses.extend(batch)
        print(f"  {subject}: {len(courses)} cours récupérés...")

        # Si on a reçu moins que la limite, c'est la dernière page
        if len(batch) < limit:
            break

        offset += limit
        time.sleep(0.2)  # politesse envers l'API

    return courses


def extract_mat_prerequisites(courses: list[dict]) -> set[str]:
    """Extrait tous les codes MAT présents dans prerequisite_courses."""
    mat_codes = set()
    mat_pattern = re.compile(r"\bMAT\d+\b")

    for course in courses:
        for prereq in course.get("prerequisite_courses", []):
            if mat_pattern.match(prereq):
                mat_codes.add(prereq)
        # Cherche aussi dans requirement_text au cas où
        text = course.get("requirement_text", "")
        for match in mat_pattern.finditer(text):
            mat_codes.add(match.group())

    return mat_codes


def fetch_individual_course(course_id: str) -> Optional[dict]:
    """Fetch un cours individuel par son ID."""
    try:
        resp = SESSION.get(
            f"{BASE_URL}/courses/{course_id}",
            params={"response_level": "full"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"  Avertissement: impossible de récupérer {course_id} ({e})")
        return None


def main():
    print("=== Fetch cours UdeM ===\n")

    # 1. Fetch tous les cours IFT
    print("Fetching cours IFT...")
    ift_courses = fetch_subject("IFT")
    print(f"  Total IFT: {len(ift_courses)} cours\n")

    # 2. Identifier les prérequis MAT
    mat_prereq_codes = extract_mat_prerequisites(ift_courses)
    print(f"Prérequis MAT identifiés: {sorted(mat_prereq_codes)}\n")

    # 3. Fetch tous les cours MAT du sujet pour avoir le contexte complet,
    #    puis compléter avec les cours individuels manquants si nécessaire
    mat_courses_all = {}

    if mat_prereq_codes:
        print("Fetching cours MAT (subject complet)...")
        mat_subject_courses = fetch_subject("MAT")
        for c in mat_subject_courses:
            mat_courses_all[c["id"]] = c
        print(f"  Total MAT depuis subject: {len(mat_courses_all)} cours\n")

        # Fetch individuellement les MAT manquants (ex: codes cross-listés)
        missing = mat_prereq_codes - mat_courses_all.keys()
        if missing:
            print(f"Fetching {len(missing)} cours MAT manquants individuellement...")
            for code in sorted(missing):
                course = fetch_individual_course(code)
                if course:
                    mat_courses_all[course["id"]] = course
                time.sleep(0.1)
            print()

    mat_courses = list(mat_courses_all.values())

    # 4. Construire et sauvegarder le résultat
    result = {
        "metadata": {
            "source": "UdeM - Planifium API",
            "base_url": BASE_URL,
            "response_level": "full",
            "ift_count": len(ift_courses),
            "mat_count": len(mat_courses),
            "mat_prerequisites_referenced": sorted(mat_prereq_codes),
        },
        "courses": {
            "IFT": ift_courses,
            "MAT": mat_courses,
        },
    }

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Sauvegardé dans {OUTPUT_FILE}")
    print(f"  IFT: {len(ift_courses)} cours")
    print(f"  MAT: {len(mat_courses)} cours")


if __name__ == "__main__":
    main()
