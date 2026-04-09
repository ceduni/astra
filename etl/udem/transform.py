"""
Lit raw_courses.json et produit canonical_courses.json avec un format normalisé.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from prereq_text_extract import augment_prerequisites

INPUT_FILE = Path(__file__).parent / "raw_courses.json"
OUTPUT_FILE = Path(__file__).parent / "canonical_courses.json"

UNIVERSITE = "UdeM"


def extract_niveau(sigle: str) -> int:
    """Extrait le niveau depuis le premier chiffre du sigle (ex: IFT1015 → 1)."""
    match = re.search(r"\d", sigle)
    return int(match.group()) if match else 0


def transform_course(course: dict, hors_perimetre: bool) -> dict:
    sigle = course["id"]
    return {
        "sigle": sigle,
        "universite": UNIVERSITE,
        "titre": course.get("name", ""),
        "credits": int(course.get("credits", 0)),
        "description": course.get("description", ""),
        "niveau": extract_niveau(sigle),
        "hors_perimetre": hors_perimetre,
        "prerequisite_courses": course.get("prerequisite_courses", []),
        "concomitant_courses": course.get("concomitant_courses", []),
        "equivalent_courses": course.get("equivalent_courses", []),
        "requirement_text": course.get("requirement_text", ""),
    }


def main():
    data = json.loads(INPUT_FILE.read_text())
    courses = data["courses"]

    program_key = "PROGRAM" if "PROGRAM" in courses else "IFT"
    program_courses = courses[program_key]
    other_courses   = courses["OTHER"]

    canonical = [
        transform_course(c, hors_perimetre=False) for c in program_courses
    ] + [
        transform_course(c, hors_perimetre=True) for c in other_courses
    ]

    # Dédoublonnage par sigle (priorité au premier trouvé)
    seen = set()
    unique = []
    for c in canonical:
        if c["sigle"] not in seen:
            seen.add(c["sigle"])
            unique.append(c)

    stats = augment_prerequisites(unique)
    print(f"  [Layer 2] +{stats['added']} prérequis extraits du texte ({stats['courses_affected']} cours affectés)")

    OUTPUT_FILE.write_text(json.dumps(unique, ensure_ascii=False, indent=2))
    print(f"Sauvegardé {len(unique)} cours dans {OUTPUT_FILE}")
    print(f"  Programme (hors_perimetre=false): {sum(1 for c in unique if not c['hors_perimetre'])}")
    print(f"  OTHER     (hors_perimetre=true):  {sum(1 for c in unique if c['hors_perimetre'])}")


if __name__ == "__main__":
    main()
