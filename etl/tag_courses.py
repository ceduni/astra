"""
Tag every Cours node by matching title + description against a keyword taxonomy.

Writes a `tags` list property to each node. Idempotent — re-running overwrites
prior tags.

Usage:
  python etl/tag_courses.py
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).parents[1] / ".env")

# ── Taxonomy ──────────────────────────────────────────────────────────────────
# Each entry: (tag_label, [keyword_substrings])
# Keywords are matched case-insensitively as substrings of (titre + description).
# Order matters only for display; all matching tags are assigned.

TAG_RULES: list[tuple[str, list[str]]] = [
    ("IA", [
        "intelligence artificielle", "machine learning", "apprentissage automatique",
        "apprentissage profond", "deep learning", "réseau de neurones",
        "réseau neuronal", "neural network", "traitement du langage naturel",
        "natural language", "vision par ordinateur", "computer vision",
        "traitement d'images", "classification supervisée", "régression logistique",
        "algorithme génétique", "système expert",
    ]),
    ("web", [
        "développement web", "application web", "interface web",
        "technologies web", "html", "css", "javascript", "http",
        "services web", "rest", "api web", "framework web",
    ]),
    ("sécurité", [
        "sécurité informatique", "sécurité des systèmes", "sécurité logicielle",
        "cybersécurité", "cryptographie", "chiffrement", "authentification",
        "vulnérabilité", "protection des données", "vie privée", "privacy",
        "malware", "attaque", "forensique", "audit de sécurité",
    ]),
    ("algorithmes", [
        "algorithme", "complexité algorithmique", "structure de données",
        "tri ", "recherche ", "programmation dynamique", "récursivité",
        "heuristique", "optimisation combinatoire", "backtracking",
        "divide and conquer", "algorithmes avancés",
    ]),
    ("bases de données", [
        "base de données", "base données", " sql", "requête sql",
        "modélisation de données", "schéma relationnel", "nosql",
        "données massives", "big data", "entrepôt de données",
        "gestion de données", "sgbd", "transactions",
    ]),
    ("systèmes", [
        "système d'exploitation", "système exploitation",
        "unix", "linux", "processus ", "thread", "mémoire virtuelle",
        "ordonnancement", "noyau", "kernel", "système embarqué",
        "temps réel", "gestion de la mémoire",
    ]),
    ("génie logiciel", [
        "génie logiciel", "conception logicielle", "architecture logicielle",
        "patron de conception", "design pattern", " uml",
        "agile", "scrum", "qualité logicielle", "test logiciel",
        "maintenance logicielle", "cycle de développement", "refactorisation",
        "métriques logicielles",
    ]),
    ("mathématiques", [
        "mathématique", "algèbre linéaire", "calcul intégral", "calcul différentiel",
        "probabilité", "statistique", "analyse numérique",
        "combinatoire", "logique mathématique", "théorie des graphes",
        "mathématiques discrètes", "équation différentielle",
    ]),
    ("réseaux", [
        "réseau informatique", "réseau de communication", "protocole réseau",
        "tcp", "udp", "routage", "commutation", "infrastructure réseau",
        "transmission de données", "topologie réseau", "sans fil",
        "mobilité réseau",
    ]),
    ("distribué", [
        "système distribué", "calcul distribué", "informatique distribuée",
        "parallèle", "parallélisme", "cloud computing",
        "microservices", "docker", "kubernetes", "hadoop", "spark",
        "tolérance aux pannes", "cohérence distribuée",
    ]),
    ("compilation", [
        "compilateur", "interpréteur", "langage de programmation",
        "analyse syntaxique", "analyse lexicale", "grammaire formelle",
        "génération de code", "automate fini", "expression régulière",
        "théorie des langages", "traduction de programmes",
    ]),
    ("interfaces", [
        "interface utilisateur", "interface graphique", "expérience utilisateur",
        "ux design", "interaction homme-machine", " ihm",
        "conception d'interfaces", "accessibilité", "design d'interaction",
        "utilisabilité", "prototypage d'interface",
    ]),
]


# ── Tagger ────────────────────────────────────────────────────────────────────

def assign_tags(titre: str, description: str) -> list[str]:
    text = ((titre or "") + " " + (description or "")).lower()
    tags = []
    for tag, keywords in TAG_RULES:
        if any(kw.lower() in text for kw in keywords):
            tags.append(tag)
    return tags


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    with driver.session() as session:
        courses = [
            dict(r["c"])
            for r in session.run("MATCH (c:Cours) RETURN c")
        ]

    tag_counts: dict[str, int] = {}
    updates = []
    for c in courses:
        tags = assign_tags(c.get("titre", ""), c.get("description", ""))
        updates.append({"sigle": c["sigle"], "tags": tags})
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    with driver.session() as session:
        session.run(
            """
            UNWIND $updates AS u
            MATCH (c:Cours {sigle: u.sigle})
            SET c.tags = u.tags
            """,
            updates=updates,
        )

    driver.close()

    tagged = sum(1 for u in updates if u["tags"])
    print(f"Tagged {tagged}/{len(updates)} courses")
    print()
    for tag, _ in TAG_RULES:
        count = tag_counts.get(tag, 0)
        bar = "█" * (count // 2)
        print(f"  {tag:<20s} {count:3d}  {bar}")


if __name__ == "__main__":
    main()
