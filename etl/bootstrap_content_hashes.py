"""
One-time bootstrap: populate content_hash on all Cours nodes that don't have one yet.

Run this BEFORE deploying the updated merge_cours change detection. After this
script runs, every Cours node will have a content_hash based on its current
titre/credits/description. Subsequent ETL runs will compare against these
hashes and flag real changes, not phantom ones.

Safe to re-run: the WHERE clause skips nodes that already have a hash.

Usage:
  python etl/bootstrap_content_hashes.py

Env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (or .env file in project root)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent))
from prereq_parser import _content_hash

load_dotenv(Path(__file__).parents[1] / ".env")

BATCH_SIZE = 500


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    with driver.session() as session:
        total = session.run(
            "MATCH (c:Cours) WHERE c.content_hash IS NULL RETURN count(c) AS n"
        ).single()["n"]

        if total == 0:
            print("All Cours nodes already have a content_hash. Nothing to do.")
            driver.close()
            return

        print(f"Populating content_hash for {total} courses (batch size {BATCH_SIZE})…")

        skip = 0
        updated = 0
        while True:
            rows = session.run(
                "MATCH (c:Cours) WHERE c.content_hash IS NULL "
                "RETURN c.sigle AS sigle, c.titre AS titre, "
                "       c.credits AS credits, c.description AS description "
                "SKIP $skip LIMIT $limit",
                skip=skip, limit=BATCH_SIZE,
            ).data()

            if not rows:
                break

            batch = [
                {"sigle": r["sigle"], "hash": _content_hash(r["titre"], r["credits"], r["description"])}
                for r in rows
            ]

            session.run(
                "UNWIND $batch AS row "
                "MATCH (c:Cours {sigle: row.sigle}) "
                "WHERE c.content_hash IS NULL "
                "SET c.content_hash = row.hash",
                batch=batch,
            )

            updated += len(batch)
            skip += BATCH_SIZE
            print(f"  {updated}/{total}", end="\r")

    driver.close()
    print(f"\nDone. {updated} courses bootstrapped.")


if __name__ == "__main__":
    main()
