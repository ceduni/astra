from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..database import get_driver

router = APIRouter(prefix="/courses", tags=["courses"])
universities_router = APIRouter(prefix="/universities", tags=["universities"])
search_router = APIRouter(tags=["search"])

# ── Programs index (loaded once at import time) ───────────────────────────────

_UNI_KEY = {"udem": "UdeM", "uqam": "UQAM", "mcgill": "McGill",
             "concordia": "Concordia", "poly": "Poly", "ets": "ETS"}

def _load_programs() -> dict:
    programs: dict = {}
    programs_dir = Path(__file__).parents[2] / "programs"
    if not programs_dir.exists():
        return programs
    for f in sorted(programs_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        display = _UNI_KEY.get(data["universite"], data["universite"])
        programs.setdefault(display, []).append({
            "id": data["programme"],
            "tous_les_cours": data["tous_les_cours"],
            "segments": data.get("segments", {}),
            "orientation_commune": data.get("orientation_commune"),
            "orientations": data.get("orientations"),
        })
    return programs

_PROGRAMS = _load_programs()


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
    tags: Optional[List[str]] = None


class CoursPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Cours]


class Universite(BaseModel):
    name: str
    total_courses: int
    program_courses: int


class CoursAccessible(Cours):
    official_equiv_sigle: Optional[str] = None


class EquivalencePair(BaseModel):
    id: str
    sigle_a: str
    titre_a: str
    universite_a: str
    sigle_b: str
    titre_b: str
    universite_b: str
    source: str
    confidence: Optional[float] = None
    status: str


class EligibilityRequest(BaseModel):
    completed: List[str]
    home_universite: Optional[str] = None


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
# Phase 1a — expand `completed` via active EQUIVAUT_A edges (undirected, 1 hop).
#
# Phase 1b — for each equivalent course (not directly completed), also add its
#            direct prerequisites to `expanded`. This is what makes cross-university
#            eligibility meaningful: completing IFT3335 (UdeM) ≡ COMP 472 (Concordia)
#            puts both COMP 472 AND its prerequisite COMP 352 into `expanded`, so
#            courses that require COMP 352 at Concordia become accessible.
#            After Phase 1b, equivalences disappear from the rest of the logic:
#            a prereq is satisfied iff its sigle is in `expanded`.
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
    OPTIONAL MATCH (:Cours {sigle: s})-[eq_r:EQUIVAUT_A]-(eq:Cours)
    WHERE eq_r.status IN ['active', 'needs_review']
    RETURN collect(DISTINCT eq.sigle) AS via_equiv
}
WITH completed_raw, [x IN completed_raw + via_equiv WHERE x IS NOT NULL] AS expanded

WITH completed_raw, expanded, [s IN expanded WHERE NOT s IN completed_raw] AS equiv_only
CALL {
    WITH equiv_only
    UNWIND equiv_only AS eq_sigle
    OPTIONAL MATCH (:Cours {sigle: eq_sigle})-[:REQUIERT]->(prereq_c:Cours)
    RETURN collect(DISTINCT prereq_c.sigle) AS via_direct_prereqs
}
WITH completed_raw, expanded, equiv_only, via_direct_prereqs
CALL {
    WITH equiv_only
    UNWIND equiv_only AS eq_sigle
    OPTIONAL MATCH (:Cours {sigle: eq_sigle})-[:REQUIERT]->(:PrerequisiteGroup)-[:INCLUDES]->(prereq_pg:Cours)
    RETURN collect(DISTINCT prereq_pg.sigle) AS via_group_prereqs
}
WITH [x IN expanded + via_direct_prereqs + via_group_prereqs WHERE x IS NOT NULL] AS expanded

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


@router.post("/eligible", response_model=List[CoursAccessible])
def get_eligible(body: EligibilityRequest):
    with get_driver().session() as session:
        rows = session.run(_ELIGIBLE_QUERY, completed=body.completed)
        courses = [dict(r["c"]) for r in rows]

    if body.home_universite:
        courses = [c for c in courses if c.get("universite") != body.home_universite]

    if not body.completed or not courses:
        return courses

    course_sigles = [c["sigle"] for c in courses]
    with get_driver().session() as session:
        equiv_rows = session.run(
            """
            MATCH (c:Cours)-[eq_r:EQUIVAUT_A {source: 'official'}]-(oc:Cours)
            WHERE eq_r.status IN ['active', 'needs_review']
              AND c.sigle IN $sigles AND oc.sigle IN $completed
            RETURN c.sigle AS sigle, oc.sigle AS equiv_sigle
            """,
            sigles=course_sigles,
            completed=body.completed,
        )
        official_equivs = {r["sigle"]: r["equiv_sigle"] for r in equiv_rows}

    return [
        {**c, "official_equiv_sigle": official_equivs.get(c["sigle"])}
        for c in courses
    ]


# ── POST /courses/eligible-graph ─────────────────────────────────────────────
#
# Same eligibility logic as /eligible but filtered to a single home university,
# plus a second pass to find prerequisite edges between the eligible courses.
# Used by the exploration graph prototype.

_EXPLORATION_ELIGIBLE_QUERY = """
WITH $completed AS completed_raw

CALL {
    WITH completed_raw
    UNWIND completed_raw AS s
    OPTIONAL MATCH (:Cours {sigle: s})-[eq_r:EQUIVAUT_A]-(eq:Cours)
    WHERE eq_r.status IN ['active', 'needs_review']
    RETURN collect(DISTINCT eq.sigle) AS via_equiv
}
WITH completed_raw, [x IN completed_raw + via_equiv WHERE x IS NOT NULL] AS expanded

WITH completed_raw, expanded, [s IN expanded WHERE NOT s IN completed_raw] AS equiv_only
CALL {
    WITH equiv_only
    UNWIND equiv_only AS eq_sigle
    OPTIONAL MATCH (:Cours {sigle: eq_sigle})-[:REQUIERT]->(prereq_c:Cours)
    RETURN collect(DISTINCT prereq_c.sigle) AS via_direct_prereqs
}
WITH completed_raw, expanded, equiv_only, via_direct_prereqs
CALL {
    WITH equiv_only
    UNWIND equiv_only AS eq_sigle
    OPTIONAL MATCH (:Cours {sigle: eq_sigle})-[:REQUIERT]->(:PrerequisiteGroup)-[:INCLUDES]->(prereq_pg:Cours)
    RETURN collect(DISTINCT prereq_pg.sigle) AS via_group_prereqs
}
WITH [x IN expanded + via_direct_prereqs + via_group_prereqs WHERE x IS NOT NULL] AS expanded

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

MATCH (c:Cours {hors_perimetre: false, universite: $home_universite})
WHERE NOT c.sigle IN expanded
  AND ($program_courses IS NULL OR c.sigle IN $program_courses)
OPTIONAL MATCH (c)-[:REQUIERT]->(t)
WITH c, t, expanded, satisfied_groups
WHERE t IS NULL
   OR (t:Cours AND t.sigle IN expanded)
   OR (t:PrerequisiteGroup AND t.id IN satisfied_groups)
WITH c, expanded
WHERE all(coreq IN [(c)-[:REQUIERT_CONCOMITANT]->(co:Cours) | co.sigle] WHERE coreq IN expanded)
RETURN c
ORDER BY c.sigle
"""

_EXPLORATION_EDGES_QUERY = """
MATCH (a:Cours)-[:REQUIERT]->(b:Cours)
WHERE a.sigle IN $sigles AND b.sigle IN $sigles
RETURN a.sigle AS source, b.sigle AS target
UNION
MATCH (a:Cours)-[:REQUIERT]->(:PrerequisiteGroup)-[:INCLUDES]->(b:Cours)
WHERE a.sigle IN $sigles AND b.sigle IN $sigles
RETURN a.sigle AS source, b.sigle AS target
"""


class ExplorationRequest(BaseModel):
    completed: List[str]
    home_universite: str
    program: Optional[str] = None


@router.get("/programs")
def get_programs():
    return {
        uni: [{"id": p["id"], "orientations": p.get("orientations")} for p in progs]
        for uni, progs in _PROGRAMS.items()
    }


def _flatten_segments(
    segments_raw: dict,
    orientation_commune: Optional[str],
    chosen_orientation: Optional[str],
) -> list:
    result = []
    for key, val in segments_raw.items():
        if not isinstance(val, dict):
            continue
        if orientation_commune is not None:
            if key != orientation_commune and key != chosen_orientation:
                continue
        if "type" in val:
            result.append({
                "id": key,
                "label": val.get("label", key),
                "type": val["type"],
                "credits_min": val.get("credits_min"),
                "credits_max": val.get("credits_max"),
                "cours": val.get("cours", []),
                "note": val.get("note"),
                "group_label": None,
            })
        else:
            group_label = val.get("label", key)
            for subkey, subval in val.items():
                if subkey == "label" or not isinstance(subval, dict):
                    continue
                result.append({
                    "id": subkey,
                    "label": subval.get("label", subkey),
                    "type": subval.get("type", "option"),
                    "credits_min": subval.get("credits_min"),
                    "credits_max": subval.get("credits_max"),
                    "cours": subval.get("cours", []),
                    "note": subval.get("note"),
                    "group_label": group_label,
                })
    return result


@router.post("/eligible-graph")
def get_eligible_graph(body: ExplorationRequest):
    program_courses = None
    if body.program and body.home_universite in _PROGRAMS:
        match = next(
            (p for p in _PROGRAMS[body.home_universite] if p["id"] == body.program),
            None,
        )
        if match:
            program_courses = match["tous_les_cours"]

    with get_driver().session() as session:
        rows = session.run(
            _EXPLORATION_ELIGIBLE_QUERY,
            completed=body.completed,
            home_universite=body.home_universite,
            program_courses=program_courses,
        )
        nodes = [dict(r["c"]) for r in rows]

    if not nodes:
        return {"nodes": [], "edges": []}

    sigles = [n["sigle"] for n in nodes]
    with get_driver().session() as session:
        edge_rows = session.run(_EXPLORATION_EDGES_QUERY, sigles=sigles)
        edges = [{"source": r["source"], "target": r["target"]} for r in edge_rows]

    return {"nodes": nodes, "edges": edges}


# ── POST /courses/program-graph ──────────────────────────────────────────────

class ProgramGraphRequest(BaseModel):
    uni: str
    program: str
    orientation: Optional[str] = None
    completed_sigles: List[str] = []


@router.post("/program-graph")
def get_program_graph(body: ProgramGraphRequest):
    program_match = next(
        (p for p in _PROGRAMS.get(body.uni, []) if p["id"] == body.program),
        None,
    )
    if program_match is None:
        raise HTTPException(status_code=404, detail=f"Program '{body.program}' not found for '{body.uni}'")

    tous_les_cours = program_match["tous_les_cours"]

    with get_driver().session() as session:
        nodes: dict = {}
        edges: list = []
        edge_ids: set = set()
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
                traverse_node(s, prereq_rec["t"], "prerequisite")
            for coreq_rec in session.run(
                "MATCH (c:Cours {sigle: $s})-[:REQUIERT_CONCOMITANT]->(t) RETURN t", s=s
            ):
                traverse_node(s, coreq_rec["t"], "corequisite")

        def traverse_node(source_id: str, node, relation_type: str):
            if "Cours" in node.labels:
                child_sigle = node["sigle"]
                eid = f"{source_id}->{child_sigle}:{relation_type}"
                if eid not in edge_ids:
                    edge_ids.add(eid)
                    edges.append({"id": eid, "source": source_id, "target": child_sigle,
                                  "relation_type": relation_type})
                traverse_course(child_sigle)
            else:
                gid = node["id"]
                if gid not in nodes:
                    nodes[gid] = {"id": gid, "node_type": "group", "data": {"type": node["type"]}}
                eid = f"{source_id}->{gid}:{relation_type}"
                if eid not in edge_ids:
                    edge_ids.add(eid)
                    edges.append({"id": eid, "source": source_id, "target": gid,
                                  "relation_type": relation_type})
                for child_rec in session.run(
                    "MATCH (g:PrerequisiteGroup {id: $id})-[:INCLUDES]->(child) RETURN child",
                    id=gid,
                ):
                    traverse_node(gid, child_rec["child"], relation_type)

        for sigle in tous_les_cours:
            traverse_course(sigle)

        seen_equiv_pairs: set = set()
        for s in list(visited_courses):
            seen_eq_for_s: set = set()
            for rec in session.run(
                "MATCH (c:Cours {sigle: $s})-[r:EQUIVAUT_A]-(eq:Cours)"
                " WHERE r.status IN ['active', 'needs_review']"
                " RETURN eq, r.source AS source, r.confidence AS confidence"
                " ORDER BY CASE r.source WHEN 'official' THEN 0 ELSE 1 END, r.confidence DESC",
                s=s,
            ):
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
                eid = f"{s}<->{eq_sigle}:equivalent"
                if eid not in edge_ids:
                    edge_ids.add(eid)
                    edges.append({"id": eid, "source": s, "target": eq_sigle,
                                  "relation_type": "equivalent", "label": "équivalent"})

        # Expand completed sigles via active equivalences so the client can
        # compute equivalence-aware availability without a second round-trip.
        expanded_completed = list(body.completed_sigles)
        if body.completed_sigles:
            eq_res = session.run(
                """
                WITH $completed AS completed
                UNWIND completed AS s
                OPTIONAL MATCH (:Cours {sigle: s})-[eq_r:EQUIVAUT_A]-(eq:Cours)
                WHERE eq_r.status IN ['active', 'needs_review']
                RETURN collect(DISTINCT eq.sigle) AS equivalents
                """,
                completed=body.completed_sigles,
            ).single()
            equivalents = (eq_res["equivalents"] if eq_res else None) or []
            expanded_completed = list(set(body.completed_sigles) | set(equivalents))

    segments = _flatten_segments(
        program_match.get("segments", {}),
        program_match.get("orientation_commune"),
        body.orientation,
    )
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "program_sigles": tous_les_cours,
        "segments": segments,
        "expanded_completed": expanded_completed,
    }


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
                "MATCH (c:Cours {sigle: $s})-[:REQUIERT_CONCOMITANT]->(t) RETURN t", s=s
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
                "MATCH (c:Cours {sigle: $s})-[r:EQUIVAUT_A]-(eq:Cours)"
                " WHERE r.status IN ['active', 'needs_review']"
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


# ── GET /equivalences ────────────────────────────────────────────────────────

@search_router.get("/equivalences", response_model=List[EquivalencePair])
def get_equivalences(
    source: Optional[str] = None,
    universite: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search in sigles and titles"),
    limit: int = Query(500, ge=1, le=2000),
):
    filters = ["r.status IN ['active', 'needs_review']"]
    params: dict = {"limit": limit}

    if source:
        filters.append("r.source = $source")
        params["source"] = source
    if universite:
        filters.append("(a.universite = $uni OR b.universite = $uni)")
        params["uni"] = universite
    if q:
        filters.append(
            "(toLower(a.sigle) CONTAINS toLower($q) OR toLower(b.sigle) CONTAINS toLower($q)"
            " OR toLower(a.titre) CONTAINS toLower($q) OR toLower(b.titre) CONTAINS toLower($q))"
        )
        params["q"] = q

    where = "WHERE " + " AND ".join(filters)
    with get_driver().session() as session:
        rows = session.run(
            f"""
            MATCH (a:Cours)-[r:EQUIVAUT_A]->(b:Cours)
            {where}
            RETURN r.id AS id,
                   a.sigle AS sigle_a, coalesce(a.titre, '') AS titre_a, a.universite AS universite_a,
                   b.sigle AS sigle_b, coalesce(b.titre, '') AS titre_b, b.universite AS universite_b,
                   r.source AS source, r.confidence AS confidence, r.status AS status
            ORDER BY CASE r.source WHEN 'official' THEN 0 ELSE 1 END,
                     CASE WHEN r.confidence IS NULL THEN 0 ELSE r.confidence END DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in rows]


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
