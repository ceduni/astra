"""
Lit raw_courses.json et produit canonical_courses.json avec un format normalisé.
"""

import json
import re
from pathlib import Path

INPUT_FILE  = Path(__file__).parent / "raw_courses.json"
OUTPUT_FILE = Path(__file__).parent / "canonical_courses.json"

UNIVERSITE = "UQAM"


def extract_niveau(sigle: str) -> int:
    match = re.search(r"\d", sigle)
    return int(match.group()) if match else 0


def transform_course(course: dict, hors_perimetre: bool) -> dict:
    sigle = course["id"]
    return {
        "sigle":                sigle,
        "universite":           UNIVERSITE,
        "titre":                course.get("name", ""),
        "credits":              int(course.get("credits", 0)),
        "description":          course.get("description", ""),
        "niveau":               extract_niveau(sigle),
        "hors_perimetre":       hors_perimetre,
        "prerequisite_courses": course.get("prerequisite_courses", []),
        "concomitant_courses":  course.get("concomitant_courses", []),
        "equivalent_courses":   course.get("equivalent_courses", []),
        "requirement_text":     course.get("requirement_text", ""),
    }


def main():
    data    = json.loads(INPUT_FILE.read_text())
    courses = data["courses"]

    inf_courses   = courses["INF"]
    other_courses = courses["OTHER"]

    # Cours hors-périmètre = cours non-INF référencés comme prérequis dans les cours INF
    inf_ids = {c["id"] for c in inf_courses}
    other_ids_referenced = {
        prereq
        for c in inf_courses
        for prereq in c.get("prerequisite_courses", []) + c.get("concomitant_courses", [])
        if prereq not in inf_ids
    }

    # Index des cours OTHER par sigle pour enrichir les stubs
    other_by_id = {c["id"]: c for c in other_courses}

    canonical = [
        transform_course(c, hors_perimetre=False) for c in inf_courses
    ] + [
        transform_course(
            other_by_id.get(sid, {
                "id": sid, "name": "", "credits": 0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            }),
            hors_perimetre=True,
        )
        for sid in sorted(other_ids_referenced)
    ]

    # Dédoublonnage par sigle
    seen, unique = set(), []
    for c in canonical:
        if c["sigle"] not in seen:
            seen.add(c["sigle"])
            unique.append(c)

    OUTPUT_FILE.write_text(json.dumps(unique, ensure_ascii=False, indent=2))
    print(f"Sauvegardé {len(unique)} cours dans {OUTPUT_FILE}")
    print(f"  INF   (hors_perimetre=false): {sum(1 for c in unique if not c['hors_perimetre'])}")
    print(f"  OTHER (hors_perimetre=true):  {sum(1 for c in unique if     c['hors_perimetre'])}")


if __name__ == "__main__":
    main()
