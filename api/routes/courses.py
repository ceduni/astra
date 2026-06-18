from __future__ import annotations

from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..database import get_driver

router = APIRouter(prefix="/courses", tags=["courses"])
universities_router = APIRouter(prefix="/universities", tags=["universities"])
search_router = APIRouter(tags=["search"])


# ── Models ────────────────────────────────────────────────────────────────────

class Cours(BaseModel):
    sigle: str
    universite: str
    titre: str
    credits: Optional[int] = None
    niveau: int
    hors_perimetre: bool
    description: str
    requirement_text: str
    # False means the scraper could not read the source page, so an empty
    # prerequisite list should be shown as 'unknown' rather than 'none'.
    # Null only on legacy nodes before backfill.
    prereqs_known: Optional[bool] = None


class CoursPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Cours]


class Universite(BaseModel):
    name: str
    total_courses: int
    program_courses: int


class EligibilityRequest(BaseModel):
    completed: List[str]


class PrereqGroup(BaseModel):
    type: str
    items: List[Union[str, PrereqGroup]]


PrereqGroup.model_rebuild()


class PrereqTree(BaseModel):
    sigle: str
    prerequisites: Optional[Union[str, PrereqGroup]] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_where(filters: list) -> str:
    return ("WHERE " + " AND ".join(filters)) if filters else ""


def _resolve(session, node) -> Union[str, dict]:
    if "Cours" in node.labels:
        return node["sigle"]
    children = list(session.run(
        "MATCH (g:PrerequisiteGroup {id: $id})-[:INCLUDES]->(child) RETURN child",
        id=node["id"],
    ))
    return {
        "type": node["type"],
        "items": [_resolve(session, record["child"]) for record in children],
    }


# ── GET /universities ─────────────────────────────────────────────────────────

@universities_router.get("", response_model=List[Universite])
def get_universities():
    with get_driver().session() as session:
        rows = session.run("""
            MATCH (c:Cours)
            RETURN c.universite AS name,
                   count(c) AS total_courses,
                   sum(CASE WHEN NOT c.hors_perimetre THEN 1 ELSE 0 END) AS program_courses
            ORDER BY name
        """)
        return [dict(r) for r in rows]


# ── GET /courses ──────────────────────────────────────────────────────────────

@router.get("", response_model=CoursPage)
def get_courses(
    universite: Optional[str] = None,
    niveau: Optional[int] = None,
    hors_perimetre: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    filters, params = [], {}

    if universite is not None:
        filters.append("c.universite = $universite")
        params["universite"] = universite
    if niveau is not None:
        filters.append("c.niveau = $niveau")
        params["niveau"] = niveau
    if hors_perimetre is not None:
        filters.append("c.hors_perimetre = $hors_perimetre")
        params["hors_perimetre"] = hors_perimetre

    where = _build_where(filters)

    with get_driver().session() as session:
        total = session.run(
            f"MATCH (c:Cours) {where} RETURN count(c) AS n", **params
        ).single()["n"]

        params["skip"] = (page - 1) * page_size
        params["limit"] = page_size
        rows = session.run(
            f"MATCH (c:Cours) {where} RETURN c ORDER BY c.universite, c.sigle"
            " SKIP $skip LIMIT $limit",
            **params,
        )
        items = [dict(r["c"]) for r in rows]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ── POST /courses/eligible ────────────────────────────────────────────────────

# Single-query eligibility resolution.
#
# Phase 1 — expand `completed` via active EQUIVAUT_A edges (undirected, 1 hop).
#           After this, equivalences disappear from the rest of the logic:
#           a prereq is satisfied iff its sigle is in `expanded`.
#
# Phase 2 — mark satisfied LEAF prerequisite groups (all INCLUDES are Cours).
#           AND => every child sigle in `expanded`; OR => any child in `expanded`.
#
# Phase 3 — mark satisfied PARENT prerequisite groups (have sub-group children).
#           Evaluates each child against `expanded` (Cours) or `leaf_satisfied`
#           (sub-group). Two passes suffice because the loader produces at most
#           depth-2 nesting (AND → OR → Cours).
#
# Phase 4 — return program courses not in `expanded` whose REQUIERT target is
#           absent / is a completed Cours / is a satisfied group, AND whose
#           REQUIERT_CONCOMITANT targets (corequisites) are all in `expanded`.
#           Corequisites are treated as blocking, same as prerequisites — a
#           conservative choice for a planning tool that doesn't model
#           "take together" scheduling.

_ELIGIBLE_QUERY = """
WITH $completed AS completed_raw

CALL {
    WITH completed_raw
    UNWIND completed_raw AS s
    OPTIONAL MATCH (:Cours {sigle: s})-[:EQUIVAUT_A {status: 'active'}]-(eq:Cours)
    RETURN collect(DISTINCT eq.sigle) AS via_equiv
}
WITH [x IN completed_raw + via_equiv WHERE x IS NOT NULL] AS expanded

CALL {
    WITH expanded
    MATCH (g:PrerequisiteGroup)
    WHERE NOT EXISTS { (g)-[:INCLUDES]->(:PrerequisiteGroup) }
    WITH g, expanded, [(g)-[:INCLUDES]->(c:Cours) | c.sigle] AS kids
    WITH g.id AS gid,
         CASE g.type
             WHEN 'AND' THEN all(k IN kids WHERE k IN expanded)
             WHEN 'OR'  THEN any(k IN kids WHERE k IN expanded)
             ELSE false
         END AS ok
    RETURN collect(CASE WHEN ok THEN gid END) AS leaf_raw
}
WITH expanded, [x IN leaf_raw WHERE x IS NOT NULL] AS leaf_satisfied

CALL {
    WITH expanded, leaf_satisfied
    MATCH (g:PrerequisiteGroup)
    WHERE EXISTS { (g)-[:INCLUDES]->(:PrerequisiteGroup) }
    WITH g, expanded, leaf_satisfied,
         [(g)-[:INCLUDES]->(c:Cours) | c.sigle IN expanded]
         + [(g)-[:INCLUDES]->(sub:PrerequisiteGroup) | sub.id IN leaf_satisfied]
         AS bools
    WITH g.id AS gid,
         CASE g.type
             WHEN 'AND' THEN all(b IN bools WHERE b)
             WHEN 'OR'  THEN any(b IN bools WHERE b)
             ELSE false
         END AS ok
    RETURN collect(CASE WHEN ok THEN gid END) AS parent_raw
}
WITH expanded,
     leaf_satisfied + [x IN parent_raw WHERE x IS NOT NULL] AS satisfied_groups

MATCH (c:Cours {hors_perimetre: false})
WHERE NOT c.sigle IN expanded
OPTIONAL MATCH (c)-[:REQUIERT]->(t)
WITH c, t, expanded, satisfied_groups
WHERE t IS NULL
   OR (t:Cours AND t.sigle IN expanded)
   OR (t:PrerequisiteGroup AND t.id IN satisfied_groups)
WITH c, expanded
WHERE all(coreq IN [(c)-[:REQUIERT_CONCOMITANT]->(co:Cours) | co.sigle] WHERE coreq IN expanded)
RETURN c
ORDER BY c.universite, c.sigle
"""


@router.post("/eligible", response_model=List[Cours])
def get_eligible(body: EligibilityRequest):
    with get_driver().session() as session:
        rows = session.run(_ELIGIBLE_QUERY, completed=body.completed)
        return [dict(r["c"]) for r in rows]


# ── GET /courses/{sigle}/prerequisite-chain ──────────────────────────────────

@router.get("/{sigle}/prerequisite-chain")
def get_prereq_chain(sigle: str):
    with get_driver().session() as session:
        if session.run("MATCH (c:Cours {sigle: $s}) RETURN c", s=sigle).single() is None:
            raise HTTPException(status_code=404, detail=f"Course '{sigle}' not found")

        nodes: dict = {}
        edges: list = []
        visited_courses: set = set()

        def traverse_course(s: str):
            if s in visited_courses:
                return
            visited_courses.add(s)
            rec = session.run("MATCH (c:Cours {sigle: $s}) RETURN c", s=s).single()
            if rec:
                nodes[s] = {"id": s, "node_type": "course", "data": dict(rec["c"])}
            prereq_rec = session.run(
                "MATCH (c:Cours {sigle: $s})-[:REQUIERT]->(t) RETURN t", s=s
            ).single()
            if prereq_rec:
                traverse_node(s, prereq_rec["t"], relation_type="prerequisite")

            coreq_recs = session.run(
                "MATCH (c:Cours {sigle: $s})-[:REQUIERT_CONCOMITANT]->(t:Cours) RETURN t", s=s
            )
            for coreq_rec in coreq_recs:
                traverse_node(s, coreq_rec["t"], relation_type="corequisite")

        def traverse_node(source_id: str, node, relation_type: str):
            if "Cours" in node.labels:
                child_sigle = node["sigle"]
                edges.append({
                    "id": f"{source_id}->{child_sigle}:{relation_type}",
                    "source": source_id,
                    "target": child_sigle,
                    "relation_type": relation_type,
                })
                traverse_course(child_sigle)
            else:
                gid = node["id"]
                if gid not in nodes:
                    nodes[gid] = {"id": gid, "node_type": "group", "data": {"type": node["type"]}}
                edges.append({
                    "id": f"{source_id}->{gid}:{relation_type}",
                    "source": source_id,
                    "target": gid,
                    "relation_type": relation_type,
                })
                children = list(session.run(
                    "MATCH (g:PrerequisiteGroup {id: $id})-[:INCLUDES]->(child) RETURN child",
                    id=gid,
                ))
                for child_rec in children:
                    traverse_node(gid, child_rec["child"], relation_type)

        traverse_course(sigle)

        # ── Equivalent courses (siblings, not traversed further) ────────────
        # For every course already in the chain, attach its active EQUIVAUT_A
        # neighbors so a student can see that a partner-university course
        # they completed already satisfies this node. These are leaves: we
        # don't walk their own prerequisites, just show the link.
        seen_equiv_pairs: set = set()
        for s in list(visited_courses):
            # Ordered so that, if a pair somehow has more than one active
            # edge (e.g. official + inferred both present), the official /
            # highest-confidence one wins rather than whichever row Neo4j
            # returns first.
            equiv_recs = session.run(
                "MATCH (c:Cours {sigle: $s})-[r:EQUIVAUT_A {status: 'active'}]-(eq:Cours)"
                " RETURN eq, r.source AS source, r.confidence AS confidence"
                " ORDER BY CASE r.source WHEN 'official' THEN 0 ELSE 1 END, r.confidence DESC",
                s=s,
            )
            seen_eq_for_s: set = set()
            for rec in equiv_recs:
                eq = rec["eq"]
                eq_sigle = eq["sigle"]
                if eq_sigle in seen_eq_for_s:
                    continue
                seen_eq_for_s.add(eq_sigle)

                pair = frozenset((s, eq_sigle))
                if pair in seen_equiv_pairs:
                    continue
                seen_equiv_pairs.add(pair)

                if eq_sigle not in nodes:
                    data = dict(eq)
                    data["is_equivalent"] = True
                    data["source"] = rec["source"]
                    data["confidence"] = rec["confidence"]
                    nodes[eq_sigle] = {"id": eq_sigle, "node_type": "course", "data": data}

                edges.append({
                    "id": f"{s}<->{eq_sigle}:equivalent",
                    "source": s,
                    "target": eq_sigle,
                    "relation_type": "equivalent",
                    "label": "équivalent",
                })

    return {"root": sigle, "nodes": list(nodes.values()), "edges": edges}


# ── GET /courses/{sigle}/prerequisites ───────────────────────────────────────

@router.get("/{sigle}/prerequisites", response_model=PrereqTree)
def get_prerequisites(sigle: str):
    with get_driver().session() as session:
        if session.run("MATCH (c:Cours {sigle: $s}) RETURN c", s=sigle).single() is None:
            raise HTTPException(status_code=404, detail=f"Course '{sigle}' not found")

        record = session.run(
            "MATCH (c:Cours {sigle: $s})-[:REQUIERT]->(t) RETURN t", s=sigle,
        ).single()
        prerequisites = _resolve(session, record["t"]) if record else None

    return {"sigle": sigle, "prerequisites": prerequisites}


# ── GET /courses/{sigle} ──────────────────────────────────────────────────────

@router.get("/{sigle}", response_model=Cours)
def get_course(sigle: str):
    with get_driver().session() as session:
        record = session.run(
            "MATCH (c:Cours {sigle: $sigle}) RETURN c", sigle=sigle,
        ).single()

    if record is None:
        raise HTTPException(status_code=404, detail=f"Course '{sigle}' not found")
    return dict(record["c"])


# ── GET /search ───────────────────────────────────────────────────────────────

@search_router.get("/search", response_model=List[Cours])
def search_courses(
    q: str = Query(..., min_length=2, description="Search in title and description"),
    universite: Optional[str] = None,
):
    filters = [
        "(toLower(c.sigle) CONTAINS toLower($q)"
        " OR toLower(c.titre) CONTAINS toLower($q)"
        " OR toLower(c.description) CONTAINS toLower($q))"
    ]
    params: dict = {"q": q}

    if universite is not None:
        filters.append("c.universite = $universite")
        params["universite"] = universite

    where = _build_where(filters)
    with get_driver().session() as session:
        rows = session.run(
            f"MATCH (c:Cours) {where} RETURN c ORDER BY c.universite, c.sigle",
            **params,
        )
        return [dict(r["c"]) for r in rows]
