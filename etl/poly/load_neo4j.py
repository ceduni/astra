"""
Lit canonical_courses.json et charge les données dans Neo4j.

Nœuds  : Cours (sigle, universite, titre, credits, description,
                  niveau, hors_perimetre, requirement_text)
Relations : (cours)-[:REQUIERT]->(prerequis)
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).parents[2] / ".env")

INPUT_FILE = Path(__file__).parent / "canonical_courses.json"

MERGE_COURS = """
MERGE (c:Cours {sigle: $sigle})
SET c.universite      = $universite,
    c.titre           = $titre,
    c.credits         = $credits,
    c.description     = $description,
    c.niveau          = $niveau,
    c.hors_perimetre  = $hors_perimetre,
    c.requirement_text = $requirement_text
"""

MERGE_REQUIERT = """
MATCH (a:Cours {sigle: $from_sigle})
MATCH (b:Cours {sigle: $to_sigle})
MERGE (a)-[:REQUIERT]->(b)
"""


def load(tx, courses: list[dict]):
    for c in courses:
        tx.run(MERGE_COURS, **{k: c[k] for k in (
            "sigle", "universite", "titre", "credits",
            "description", "niveau", "hors_perimetre", "requirement_text",
        )})

    for c in courses:
        for prereq in c.get("prerequisite_courses", []):
            tx.run(MERGE_REQUIERT, from_sigle=c["sigle"], to_sigle=prereq)


def main():
    courses = json.loads(INPUT_FILE.read_text())

    uri      = os.environ["NEO4J_URI"]
    user     = os.environ["NEO4J_USER"]
    password = os.environ["NEO4J_PASSWORD"]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        session.execute_write(load, courses)

    driver.close()

    rels = sum(len(c.get("prerequisite_courses", [])) for c in courses)
    print(f"Chargé {len(courses)} nœuds Cours et {rels} relations REQUIERT.")


if __name__ == "__main__":
    main()
