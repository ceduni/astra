"""
Lit raw_courses.json et produit canonical_courses.json avec un format normalisé.
"""

import json
import re
from pathlib import Path

INPUT_FILE  = Path(__file__).parent / "raw_courses.json"
OUTPUT_FILE = Path(__file__).parent / "canonical_courses.json"

UNIVERSITE = "Poly"


def extract_niveau(sigle: str) -> int:
    match = re.search(r"\d", sigle)
    return int(match.group()) if match else 0


def transform_course(course: dict, hors_perimetre: bool) -> dict:
    sigle = course["id"]
    return {
        "sigle":                sigle,
        "universite":           UNIVERSITE,
        "titre":                course.get("name", ""),
        "credits":              int(course["credits"]) if course.get("credits") else None,
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

    program_courses = courses["PROGRAM"]
    other_courses   = courses["OTHER"]

    canonical = [
        transform_course(c, hors_perimetre=False) for c in program_courses
    ] + [
        transform_course(c, hors_perimetre=True)  for c in other_courses
    ]

    # Dédoublonnage par sigle
    seen, unique = set(), []
    for c in canonical:
        if c["sigle"] not in seen:
            seen.add(c["sigle"])
            unique.append(c)

    OUTPUT_FILE.write_text(json.dumps(unique, ensure_ascii=False, indent=2))
    print(f"Sauvegardé {len(unique)} cours dans {OUTPUT_FILE}")
    print(f"  Programme (hors_perimetre=false): {sum(1 for c in unique if not c['hors_perimetre'])}")
    print(f"  OTHER     (hors_perimetre=true):  {sum(1 for c in unique if     c['hors_perimetre'])}")


if __name__ == "__main__":
    main()
