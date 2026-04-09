"""
Shared prerequisite parser for all university ETL loaders.

parse_prereqs(prereq_courses, req_text) -> list
  Analyzes requirement_text to infer AND/OR structure.
  Returns a flat list where:
    - each str item  → course sigle, AND-connected at top level
    - each list item → OR group (list of sigles)

  Interpretation of the returned value `items`:
    len == 0              → no prerequisites
    len == 1, str         → single direct REQUIERT
    len == 1, list        → single OR group
    len > 1, all strs     → AND group of direct courses
    len > 1, mixed        → AND group; sub-lists are OR groups

load_prereqs(tx, from_sigle, items, stats)
  Writes the parsed structure into Neo4j.
  Updates stats dict keys: 'direct', 'and', 'or'.

clear_uni_prereqs(session, universite)
  Removes all REQUIERT edges and PrerequisiteGroup nodes
  that belong to a given university before a reload.
"""

import re

OR_RE = re.compile(r"\b(ou|or)\b", re.IGNORECASE)


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_prereqs(prereq_courses: list, req_text: str) -> list:
    """
    Return the AND/OR structure of prereq_courses as described above.
    Uses req_text to detect connectors between adjacent course codes.
    Falls back to a plain AND list when text is missing or codes are absent.
    """
    if not prereq_courses:
        return []
    if len(prereq_courses) == 1:
        return [prereq_courses[0]]

    text = req_text or ""

    # Locate each prereq code's first occurrence in the text (case-insensitive)
    text_up = text.upper()
    positions = []
    for code in prereq_courses:
        idx = text_up.find(code.upper())
        if idx >= 0:
            positions.append((idx, code))

    # Need at least 2 codes found in text to detect connectors
    if len(positions) < 2:
        # Fallback: check global OR/AND signal
        if OR_RE.search(text) and not re.search(r"\b(et|and)\b", text, re.IGNORECASE):
            return [list(prereq_courses)]   # pure OR group
        return list(prereq_courses)         # AND (each direct)

    positions.sort()

    # Group adjacent codes by the connector between them:
    #   OR_RE match between two codes → same OR segment
    #   anything else                 → AND boundary → new segment
    segments = [[positions[0][1]]]
    for i in range(1, len(positions)):
        prev_end   = positions[i - 1][0] + len(positions[i - 1][1])
        curr_start = positions[i][0]
        between    = text[prev_end:curr_start]

        if OR_RE.search(between):
            segments[-1].append(positions[i][1])
        else:
            segments.append([positions[i][1]])

    # Codes not found in text → append as extra AND items
    found_up = {p[1].upper() for p in positions}
    for code in prereq_courses:
        if code.upper() not in found_up:
            segments.append([code])

    # Flatten: single-element segments → str; multi-element → list (OR group)
    result = [seg[0] if len(seg) == 1 else seg for seg in segments]
    return result


# ── Neo4j helpers ─────────────────────────────────────────────────────────────

_MERGE_COURS = """
MERGE (c:Cours {sigle: $sigle})
SET c.universite       = $universite,
    c.titre            = $titre,
    c.credits          = $credits,
    c.description      = $description,
    c.niveau           = $niveau,
    c.hors_perimetre   = $hors_perimetre,
    c.requirement_text = $requirement_text
"""

_COURS_FIELDS = (
    "sigle", "universite", "titre", "credits",
    "description", "niveau", "hors_perimetre", "requirement_text",
)


def merge_cours(tx, course: dict):
    tx.run(_MERGE_COURS, **{k: course[k] for k in _COURS_FIELDS})


def load_prereqs(tx, from_sigle: str, items: list, stats: dict):
    """Write parsed prerequisite structure to Neo4j, updating stats."""
    if not items:
        return

    if len(items) == 1:
        item = items[0]
        if isinstance(item, str):
            # ── direct REQUIERT ──────────────────────────────────────────────
            tx.run(
                "MATCH (a:Cours {sigle:$f}) MATCH (b:Cours {sigle:$t})"
                " MERGE (a)-[:REQUIERT]->(b)",
                f=from_sigle, t=item,
            )
            stats["direct"] += 1
        else:
            # ── single OR group ──────────────────────────────────────────────
            gid = f"{from_sigle}__OR"
            _create_or_group(tx, from_sigle, gid, item, parent_is_cours=True)
            stats["or"] += 1
        return

    # ── AND group (possibly with OR sub-groups) ──────────────────────────────
    and_id = f"{from_sigle}__AND"
    tx.run(
        "MERGE (g:PrerequisiteGroup {id:$id}) SET g.type='AND'",
        id=and_id,
    )
    tx.run(
        "MATCH (a:Cours {sigle:$f}) MATCH (g:PrerequisiteGroup {id:$id})"
        " MERGE (a)-[:REQUIERT]->(g)",
        f=from_sigle, id=and_id,
    )
    stats["and"] += 1

    for i, item in enumerate(items):
        if isinstance(item, str):
            tx.run(
                "MATCH (ag:PrerequisiteGroup {id:$aid})"
                " MATCH (b:Cours {sigle:$t})"
                " MERGE (ag)-[:INCLUDES]->(b)",
                aid=and_id, t=item,
            )
        else:
            or_id = f"{from_sigle}__OR_{i}"
            tx.run(
                "MERGE (g:PrerequisiteGroup {id:$id}) SET g.type='OR'",
                id=or_id,
            )
            tx.run(
                "MATCH (ag:PrerequisiteGroup {id:$aid})"
                " MATCH (og:PrerequisiteGroup {id:$oid})"
                " MERGE (ag)-[:INCLUDES]->(og)",
                aid=and_id, oid=or_id,
            )
            for code in item:
                tx.run(
                    "MATCH (og:PrerequisiteGroup {id:$oid})"
                    " MATCH (b:Cours {sigle:$t})"
                    " MERGE (og)-[:INCLUDES]->(b)",
                    oid=or_id, t=code,
                )
            stats["or"] += 1


def _create_or_group(tx, from_sigle, gid, codes, parent_is_cours):
    tx.run(
        "MERGE (g:PrerequisiteGroup {id:$id}) SET g.type='OR'",
        id=gid,
    )
    if parent_is_cours:
        tx.run(
            "MATCH (a:Cours {sigle:$f}) MATCH (g:PrerequisiteGroup {id:$id})"
            " MERGE (a)-[:REQUIERT]->(g)",
            f=from_sigle, id=gid,
        )
    for code in codes:
        tx.run(
            "MATCH (g:PrerequisiteGroup {id:$id}) MATCH (b:Cours {sigle:$t})"
            " MERGE (g)-[:INCLUDES]->(b)",
            id=gid, t=code,
        )


# ── Clear before reload ───────────────────────────────────────────────────────

def clear_uni_prereqs(session, universite: str):
    """
    Remove all prerequisite structure for one university:
      1. PrerequisiteGroup nodes reachable from this uni's courses
         (top-level AND/OR and nested OR sub-groups via INCLUDES).
      2. Any remaining direct REQUIERT Cours→Cours edges.
    """
    # Step 1a: delete nested OR sub-groups (inside AND groups)
    session.run("""
        MATCH (c:Cours {universite: $uni})-[:REQUIERT]->(g:PrerequisiteGroup)
        OPTIONAL MATCH (g)-[:INCLUDES]->(sub:PrerequisiteGroup)
        DETACH DELETE sub
    """, uni=universite)

    # Step 1b: delete top-level PrerequisiteGroup nodes
    #          (DETACH DELETE also removes the REQUIERT edge from Cours)
    session.run("""
        MATCH (c:Cours {universite: $uni})-[:REQUIERT]->(g:PrerequisiteGroup)
        DETACH DELETE g
    """, uni=universite)

    # Step 2: delete remaining direct Cours→Cours REQUIERT edges
    session.run("""
        MATCH (c:Cours {universite: $uni})-[r:REQUIERT]->(:Cours)
        DELETE r
    """, uni=universite)
