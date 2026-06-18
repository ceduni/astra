"""
One-shot backfill for the Cours.prereqs_known property.

Computes the flag for every existing Cours node based on current graph
state — no scraping, no canonical-file rewrites. Safe to re-run; the
underlying SET is idempotent.

After this runs once, future ETL loads keep the flag fresh via
set_prereqs_known() called from each university's load_neo4j.py.

  python etl/backfill_prereqs_known.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent))
from prereq_parser import set_prereqs_known

load_dotenv(Path(__file__).parents[1] / ".env")


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    with driver.session() as session:
        unis = [r["u"] for r in session.run(
            "MATCH (c:Cours) RETURN DISTINCT c.universite AS u ORDER BY u"
        )]

        for uni in unis:
            updated = set_prereqs_known(session, uni)
            unknown = session.run(
                "MATCH (c:Cours {universite: $u, prereqs_known: false}) "
                "RETURN count(c) AS n",
                u=uni,
            ).single()["n"]
            print(f"  [{uni:10s}] updated={updated:4d}  unknown={unknown:4d}")

    driver.close()


if __name__ == "__main__":
    main()
