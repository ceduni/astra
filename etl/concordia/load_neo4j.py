"""
Lit canonical_courses.json et charge les données dans Neo4j.

Nœuds     : Cours
Relations : (Cours)-[:REQUIERT]->(Cours)              direct (1 prérequis)
            (Cours)-[:REQUIERT]->(PrerequisiteGroup)  groupe AND ou OR
            (PrerequisiteGroup)-[:INCLUDES]->(Cours | PrerequisiteGroup)
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parents[1]))
from prereq_parser import merge_cours, load_prereqs, clear_uni_prereqs, parse_prereqs

load_dotenv(Path(__file__).parents[2] / ".env")

INPUT_FILE = Path(__file__).parent / "canonical_courses.json"
UNIVERSITE = "Concordia"


def load(tx, courses: list, stats: dict):
    for c in courses:
        merge_cours(tx, c)

    for c in courses:
        prereqs = c.get("prerequisite_courses", [])
        if not prereqs:
            continue
        items = parse_prereqs(prereqs, c.get("requirement_text", ""))
        load_prereqs(tx, c["sigle"], items, stats)


def main():
    courses = json.loads(INPUT_FILE.read_text())
    stats = {"direct": 0, "and": 0, "or": 0}

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    with driver.session() as session:
        clear_uni_prereqs(session, UNIVERSITE)
        session.execute_write(load, courses, stats)
    driver.close()

    print(f"[{UNIVERSITE}] {len(courses)} nœuds Cours")
    print(f"  {stats['direct']:3d} relations directes  (1 prérequis)")
    print(f"  {stats['and']:3d} groupes AND")
    print(f"  {stats['or']:3d} groupes OR")


if __name__ == "__main__":
    main()
