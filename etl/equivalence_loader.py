"""
ETL-side writer for EQUIVAUT_A relationships.

CONTRACT
--------
This module is the ONLY place in the ETL pipeline allowed to write or
delete EQUIVAUT_A edges. All operations here are restricted to
`source = 'inferred'`.

Edges with `source = 'official'` or `source = 'request'` are owned by
the API (admin endpoints, request workflow). The ETL must never see them.

If you find yourself needing to bypass this restriction in an ETL script,
stop — the equivalence belongs to a different lifecycle and should be
written via the API instead.
"""

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

INFERRED = "inferred"
VERSION = "v1"


def clear_inferred_equivalences(session, universite: str) -> int:
    """
    Delete all `source = 'inferred'` EQUIVAUT_A edges where at least
    one endpoint belongs to `universite`. Returns the deletion count.

    Scoped per-university so a partial reload of one university does
    not invalidate inferred edges between two other universities.
    """
    result = session.run(
        """
        MATCH (a:Cours)-[r:EQUIVAUT_A {source: $source}]-(b:Cours)
        WHERE a.universite = $uni OR b.universite = $uni
        DELETE r
        RETURN count(r) AS deleted
        """,
        source=INFERRED, uni=universite,
    ).single()
    return result["deleted"] if result else 0


def write_inferred_equivalence(
    tx,
    sigle_a: str,
    sigle_b: str,
    confidence: float,
    evidence: str = "",
) -> str:
    """
    Create a single inferred equivalence edge. Returns the new edge id.

    No MERGE — inferred edges are wiped wholesale before each rebuild,
    so duplicates can't accumulate. Using CREATE keeps the write cheap.
    """
    edge_id = str(uuid4())
    tx.run(
        """
        MATCH (a:Cours {sigle: $a}), (b:Cours {sigle: $b})
        CREATE (a)-[:EQUIVAUT_A {
            id:         $id,
            source:     $source,
            status:     'active',
            created_at: datetime($created_at),
            created_by: 'etl',
            confidence: $confidence,
            evidence:   $evidence,
            version:    $version
        }]->(b)
        """,
        a=sigle_a, b=sigle_b, id=edge_id, source=INFERRED,
        created_at=datetime.now(timezone.utc).isoformat(),
        confidence=confidence, evidence=evidence, version=VERSION,
    )
    return edge_id


def write_inferred_batch(tx, pairs: Iterable[dict]) -> int:
    """
    Bulk-insert inferred equivalences.

    `pairs` is an iterable of dicts with keys:
      sigle_a, sigle_b, confidence, evidence (optional)
    """
    count = 0
    for p in pairs:
        write_inferred_equivalence(
            tx,
            sigle_a=p["sigle_a"],
            sigle_b=p["sigle_b"],
            confidence=p["confidence"],
            evidence=p.get("evidence", ""),
        )
        count += 1
    return count
