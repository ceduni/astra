"""
Fetch les cours du Baccalauréat en informatique (B. Sc.) de l'UdeM.

Stratégie :
  1. GET /api/v1/programs → trouver le programme 117510 → extraire la liste
     des 148 cours du programme (tous segments et blocs confondus).
  2. GET /api/v1/courses?response_level=full → récupérer tous les cours en
     un appel (l'API ignore les filtres serveur), filtrer côté client.
  3. Cours du programme → PROGRAM (hors_perimetre: false).
     Prérequis référencés hors programme → OTHER (hors_perimetre: true).

Sauvegarde dans etl/udem/raw_courses.json.
"""

import json
from pathlib import Path

import requests

BASE_URL    = "https://planifium-api.onrender.com/api/v1"
PROGRAM_ID  = "117510"   # Baccalauréat en informatique (B. Sc.)
OUTPUT_FILE = Path(__file__).parent / "raw_courses.json"


def fetch_program_course_ids() -> list[str]:
    """
    Retourne la liste ordonnée des IDs de cours du programme 117510,
    tels que définis dans prog['courses'] (union de tous les blocs).
    """
    print(f"Fetching programme {PROGRAM_ID}...")
    resp = requests.get(f"{BASE_URL}/programs", timeout=120)
    resp.raise_for_status()
    programs = resp.json()

    prog = next((p for p in programs if p["id"] == PROGRAM_ID), None)
    if prog is None:
        raise RuntimeError(f"Programme {PROGRAM_ID} introuvable.")

    print(f"  Trouvé : {prog['name']}")
    print(f"  Segments : {len(prog['segments'])}, cours listés : {len(prog['courses'])}")
    return prog["courses"]


def fetch_all_courses() -> list[dict]:
    """Fetch tous les cours (l'API ignore les filtres serveur)."""
    print("\nFetching tous les cours (response_level=full)...")
    resp = requests.get(
        f"{BASE_URL}/courses",
        params={"response_level": "full"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    courses = data if isinstance(data, list) else data.get("courses", data.get("items", []))
    print(f"  {len(courses)} cours récupérés.")
    return courses


def main():
    # 1. IDs du programme
    program_ids = fetch_program_course_ids()
    program_id_set = set(program_ids)

    # 2. Tous les cours de l'API
    all_courses = fetch_all_courses()
    by_id = {c["id"]: c for c in all_courses}

    # 3. Cours du programme (dédoublonnage : un cours peut figurer dans plusieurs segments)
    program_courses: list[dict] = []
    missing_program: list[str] = []
    seen_program: set[str] = set()
    for cid in program_ids:
        if cid in seen_program:
            continue
        seen_program.add(cid)
        if cid in by_id:
            program_courses.append(by_id[cid])
        else:
            missing_program.append(cid)

    if missing_program:
        print(f"\n  Attention : {len(missing_program)} cours du programme introuvables dans l'API :")
        for cid in missing_program:
            print(f"    {cid}")

    # 4. Prérequis hors programme
    other_ids: set[str] = set()
    for c in program_courses:
        for dep in c.get("prerequisite_courses", []) + c.get("concomitant_courses", []):
            if dep not in program_id_set:
                other_ids.add(dep)

    other_courses: list[dict] = []
    missing_other: list[str] = []
    for cid in sorted(other_ids):
        if cid in by_id:
            other_courses.append(by_id[cid])
        else:
            missing_other.append(cid)
            other_courses.append({
                "id": cid, "name": "", "credits": 0, "description": "",
                "prerequisite_courses": [], "concomitant_courses": [],
                "equivalent_courses": [], "requirement_text": "",
            })

    # 5. Sauvegarder
    subjects = sorted({c["id"][:3] for c in program_courses})
    result = {
        "metadata": {
            "source":          f"UdeM – Planifium API – programme {PROGRAM_ID}",
            "program_name":    "Baccalauréat en informatique (B. Sc.)",
            "program_id":      PROGRAM_ID,
            "program_count":   len(program_courses),
            "other_count":     len(other_courses),
            "subjects":        subjects,
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
    if missing_other:
        print(f"  (dont {len(missing_other)} stubs introuvables dans l'API : {missing_other})")


if __name__ == "__main__":
    main()
