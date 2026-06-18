"""
One-shot loader for officially-confirmed course equivalences.

Reads a flat JSON export (UdeM course -> list of equivalent courses at
partner universities) and creates EQUIVAUT_A {source: 'official',
status: 'active', confidence: 1.0} edges via the admin API.

This does NOT write to Neo4j directly. Per etl/equivalence_loader.py's
contract, ETL scripts may only write source='inferred' edges — 'official'
and 'request' edges belong to the API's lifecycle (POST /admin/equivalences
already validates both endpoints exist and stamps the right fields).
Requires the API to be running.

Each equivalence is created as two directed edges (A->B and B->A) so the
relationship reads the same starting from either course.

Equivalences referencing ÉTS or Université Laval are skipped — neither
university has been scraped yet, so their course codes aren't in the graph.

Not idempotent: re-running creates duplicate edges for pairs already loaded
(the admin API uses CREATE, not MERGE).

Usage:
  python etl/load_official_equivalences.py [path/to/equivalences.json]

Env:
  API_BASE_URL  defaults to http://localhost:8000
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# Universities not yet scraped — their course codes aren't in the graph.
SKIP_UNIVERSITIES = {"ETS", "ULAVAL"}

# Concordia and McGill sigles carry a space between the subject letters and
# the course number (e.g. "COMP 472"); this equivalences export omits it.
SPACE_UNIVERSITIES = {"CONCORDIA", "MCGILL"}
_SIGLE_RE = re.compile(r"^([A-Za-z]+)\s*(\d.*)$")


def normalize_sigle(code: str, university_id: str) -> str:
    if university_id not in SPACE_UNIVERSITIES:
        return code
    m = _SIGLE_RE.match(code)
    return f"{m.group(1)} {m.group(2)}" if m else code


def post_equivalence(sigle_a: str, sigle_b: str) -> tuple[bool, str]:
    """POST one directed edge to the admin API. Returns (created, detail)."""
    body = json.dumps({
        "sigle_a": sigle_a,
        "sigle_b": sigle_b,
        "source": "official",
        "confidence": 1.0,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE_URL}/admin/equivalences",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
        return True, ""
    except urllib.error.HTTPError as e:
        return False, e.read().decode()


def main():
    default_input = Path(__file__).parent / "official_equivalences.json"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input
    courses = json.loads(path.read_text())

    created = 0
    skipped_university = 0
    skipped_missing: list[tuple[str, str, str]] = []

    for course in courses:
        sigle_a = course["code"]
        for eq in course.get("equivalences", []):
            university_id = eq["university"]["id"]

            if university_id in SKIP_UNIVERSITIES:
                skipped_university += 1
                continue

            sigle_b = normalize_sigle(eq["code"], university_id)

            for a, b in ((sigle_a, sigle_b), (sigle_b, sigle_a)):
                ok, detail = post_equivalence(a, b)
                if ok:
                    created += 1
                else:
                    skipped_missing.append((a, b, detail))

    print(f"Created:                                {created} EQUIVAUT_A edges")
    print(f"Skipped (ÉTS/ULaval, not yet scraped):   {skipped_university} equivalences")
    print(f"Skipped (course not found in graph):     {len(skipped_missing)} edge attempts")
    for a, b, detail in skipped_missing:
        print(f"  {a} -> {b}: {detail}")


if __name__ == "__main__":
    main()
