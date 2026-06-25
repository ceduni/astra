"""
Idempotent Neo4j schema setup: constraints and indexes.

Run once after a fresh database, and safely re-run any time —
all statements use IF NOT EXISTS.

  python etl/setup_schema.py

Constraints
-----------
- Cours.sigle UNIQUE
    Sigles are the primary key of the catalogue. Every loader MERGEs on
    sigle, so uniqueness is already assumed; this makes it enforced.

- EQUIVAUT_A.id UNIQUE (relationship property constraint)
    Each equivalence edge carries a UUID `id` for direct lookup by the
    admin endpoints. Required so DELETE / GET by id never matches more
    than one edge.

Indexes
-------
- EQUIVAUT_A(source)
    Eligibility queries will filter by source (e.g. ignore low-confidence
    inferred, or restrict per-session requests). Low cardinality but
    queried on every eligibility check once equivalences land.

- EQUIVAUT_A(status)
    Same reason — only `active` edges affect eligibility.

Relationship types (not enforced here, listed for reference)
--------------------------------------------------------------
- REQUIERT               Cours/PrerequisiteGroup prerequisite edges.
- REQUIERT_CONCOMITANT   Direct Cours→Cours corequisite edges, loaded from
    concomitant_courses. No grouping (AND/OR) is modeled — every entry is
    a flat requirement. Traversal always starts from an already-matched
    Cours node, so no index is needed.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).parents[1] / ".env")


STATEMENTS = [
    # ── Node constraints ─────────────────────────────────────────────────────
    """
    CREATE CONSTRAINT cours_sigle_unique IF NOT EXISTS
    FOR (c:Cours) REQUIRE c.sigle IS UNIQUE
    """,

    # ── Relationship constraints (Neo4j 5.7+) ────────────────────────────────
    """
    CREATE CONSTRAINT equivaut_a_id_unique IF NOT EXISTS
    FOR ()-[r:EQUIVAUT_A]-() REQUIRE r.id IS UNIQUE
    """,

    # ── Relationship indexes ─────────────────────────────────────────────────
    """
    CREATE INDEX equivaut_a_source IF NOT EXISTS
    FOR ()-[r:EQUIVAUT_A]-() ON (r.source)
    """,
    """
    CREATE INDEX equivaut_a_status IF NOT EXISTS
    FOR ()-[r:EQUIVAUT_A]-() ON (r.status)
    """,

    # ── Version indexes ──────────────────────────────────────────────────────
    """
    CREATE INDEX cours_version IF NOT EXISTS
    FOR (c:Cours) ON (c.version)
    """,
    """
    CREATE INDEX requiert_version IF NOT EXISTS
    FOR ()-[r:REQUIERT]-() ON (r.version)
    """,
    """
    CREATE INDEX equivaut_a_version IF NOT EXISTS
    FOR ()-[r:EQUIVAUT_A]-() ON (r.version)
    """,
]


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    with driver.session() as session:
        for stmt in STATEMENTS:
            session.run(stmt)
            label = " ".join(stmt.split()[:3])
            print(f"  ✓ {label} ...")
    driver.close()
    print("Schema ready.")


if __name__ == "__main__":
    main()
