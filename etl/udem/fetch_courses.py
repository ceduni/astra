"""
Fetch tous les cours de l'UdeM (response_level=full),
filtre les cours IFT, identifie les prérequis MAT référencés,
filtre aussi les cours MAT, et sauvegarde dans raw_courses.json.

Note: l'API retourne tous les cours en une seule réponse (pas de filtrage serveur),
donc on récupère tout et on filtre côté client.
"""

import json
import re
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://planifium-api.onrender.com/api/v1"
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"


def fetch_all_courses() -> list[dict]:
    """Fetch tous les cours avec response_level=full."""
    print("Fetching tous les cours (response_level=full)...")
    resp = requests.get(
        f"{BASE_URL}/courses",
        params={"response_level": "full"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        return data
    return data.get("courses", data.get("items", data.get("results", [])))


def filter_by_subject(courses: list[dict], subject: str) -> list[dict]:
    """Filtre les cours dont l'ID commence par le préfixe du sujet."""
    prefix = subject.upper()
    return [c for c in courses if c.get("id", "").upper().startswith(prefix)]


def extract_mat_prerequisites(courses: list[dict]) -> set[str]:
    """Extrait tous les codes MAT présents dans prerequisite_courses ou requirement_text."""
    mat_codes = set()
    mat_pattern = re.compile(r"\bMAT\d+\b")

    for course in courses:
        for prereq in course.get("prerequisite_courses", []):
            if mat_pattern.match(prereq):
                mat_codes.add(prereq)
        for match in mat_pattern.finditer(course.get("requirement_text", "")):
            mat_codes.add(match.group())

    return mat_codes


def main():
    print("=== Fetch cours UdeM ===\n")

    # 1. Récupérer tous les cours en un seul appel
    all_courses = fetch_all_courses()
    print(f"  Total récupéré: {len(all_courses)} cours\n")

    # 2. Filtrer les cours IFT
    ift_courses = filter_by_subject(all_courses, "IFT")
    print(f"Cours IFT: {len(ift_courses)}")

    # 3. Identifier les prérequis MAT dans les cours IFT
    mat_prereq_codes = extract_mat_prerequisites(ift_courses)
    print(f"Prérequis MAT référencés: {sorted(mat_prereq_codes)}\n")

    # 4. Filtrer les cours MAT
    mat_courses = filter_by_subject(all_courses, "MAT")
    mat_courses_by_id = {c["id"]: c for c in mat_courses}
    print(f"Cours MAT disponibles: {len(mat_courses)}")

    # Vérifier si tous les prérequis MAT sont couverts
    missing = mat_prereq_codes - mat_courses_by_id.keys()
    if missing:
        print(f"  Attention: prérequis MAT introuvables dans l'API: {sorted(missing)}")

    # 5. Construire et sauvegarder le résultat
    result = {
        "metadata": {
            "source": "UdeM - Planifium API",
            "base_url": BASE_URL,
            "response_level": "full",
            "total_courses_fetched": len(all_courses),
            "ift_count": len(ift_courses),
            "mat_count": len(mat_courses),
            "mat_prerequisites_referenced": sorted(mat_prereq_codes),
            "mat_prerequisites_missing": sorted(missing) if missing else [],
        },
        "courses": {
            "IFT": ift_courses,
            "MAT": mat_courses,
        },
    }

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSauvegardé dans {OUTPUT_FILE}")
    print(f"  IFT: {len(ift_courses)} cours")
    print(f"  MAT: {len(mat_courses)} cours")


if __name__ == "__main__":
    main()
