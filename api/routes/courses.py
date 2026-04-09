from __future__ import annotations

from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_driver

router = APIRouter(prefix="/courses", tags=["courses"])


class Cours(BaseModel):
    sigle: str
    universite: str
    titre: str
    credits: int
    niveau: int
    hors_perimetre: bool
    description: str
    requirement_text: str


class EligibilityRequest(BaseModel):
    completed: List[str]


class PrereqGroup(BaseModel):
    type: str                                   # 'AND' or 'OR'
    items: List[Union[str, PrereqGroup]]        # sigle or nested group


PrereqGroup.model_rebuild()


class PrereqTree(BaseModel):
    sigle: str
    prerequisites: Optional[Union[str, PrereqGroup]] = None


@router.get("", response_model=list[Cours])
def get_courses(
    universite: Optional[str] = None,
    niveau: Optional[int] = None,
    hors_perimetre: Optional[bool] = None,
):
    filters = []
    params = {}

    if universite is not None:
        filters.append("c.universite = $universite")
        params["universite"] = universite
    if niveau is not None:
        filters.append("c.niveau = $niveau")
        params["niveau"] = niveau
    if hors_perimetre is not None:
        filters.append("c.hors_perimetre = $hors_perimetre")
        params["hors_perimetre"] = hors_perimetre

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    query = f"MATCH (c:Cours) {where} RETURN c ORDER BY c.universite, c.sigle"

    with get_driver().session() as session:
        result = session.run(query, **params)
        return [dict(record["c"]) for record in result]


def _prereq_satisfied(node_ref, completed: set, groups: dict) -> bool:
    """
    Recursively evaluate whether a prerequisite node is satisfied.
    node_ref: ('course', sigle) | ('group', group_id)
    groups: {group_id: {'type': 'AND'|'OR', 'items': [node_ref, ...]}}
    """
    kind, val = node_ref
    if kind == "course":
        return val in completed
    group = groups[val]
    check = all if group["type"] == "AND" else any
    return check(_prereq_satisfied(item, completed, groups) for item in group["items"])


def _resolve(session, node) -> Union[str, dict]:
    """Recursively resolve a Cours or PrerequisiteGroup node into a tree."""
    if "Cours" in node.labels:
        return node["sigle"]

    # PrerequisiteGroup — fetch its INCLUDES targets
    # Iterate directly (not .data()) to preserve Neo4j node objects with .labels
    children = list(session.run(
        "MATCH (g:PrerequisiteGroup {id: $id})-[:INCLUDES]->(child) RETURN child",
        id=node["id"],
    ))
    return {
        "type": node["type"],
        "items": [_resolve(session, record["child"]) for record in children],
    }


@router.post("/eligible", response_model=List[Cours])
def get_eligible(body: EligibilityRequest):
    completed = set(body.completed)

    with get_driver().session() as session:
        # Query 1: every in-program course + its single REQUIERT target (if any)
        course_rows = list(session.run("""
            MATCH (c:Cours {hors_perimetre: false})
            OPTIONAL MATCH (c)-[:REQUIERT]->(t)
            RETURN c, t
        """))

        # Query 2: full PrerequisiteGroup structure (all INCLUDES edges)
        pg_rows = list(session.run("""
            MATCH (g:PrerequisiteGroup)-[:INCLUDES]->(child)
            RETURN g.id AS gid, g.type AS gtype, child
        """))

    # Build in-memory group map
    groups: dict = {}
    for row in pg_rows:
        gid, gtype, child = row["gid"], row["gtype"], row["child"]
        if gid not in groups:
            groups[gid] = {"type": gtype, "items": []}
        if "Cours" in child.labels:
            groups[gid]["items"].append(("course", child["sigle"]))
        else:
            groups[gid]["items"].append(("group", child["id"]))

    eligible = []
    for row in course_rows:
        c, t = row["c"], row["t"]
        sigle = c["sigle"]

        if sigle in completed:
            continue

        if t is None:
            eligible.append(dict(c))
        elif "Cours" in t.labels:
            if t["sigle"] in completed:
                eligible.append(dict(c))
        else:  # PrerequisiteGroup
            if _prereq_satisfied(("group", t["id"]), completed, groups):
                eligible.append(dict(c))

    eligible.sort(key=lambda c: (c["universite"], c["sigle"]))
    return eligible


@router.get("/{sigle}/prerequisites", response_model=PrereqTree)
def get_prerequisites(sigle: str):
    with get_driver().session() as session:
        if session.run("MATCH (c:Cours {sigle: $s}) RETURN c", s=sigle).single() is None:
            raise HTTPException(status_code=404, detail=f"Course '{sigle}' not found")

        record = session.run(
            "MATCH (c:Cours {sigle: $s})-[:REQUIERT]->(t) RETURN t",
            s=sigle,
        ).single()

        prerequisites = _resolve(session, record["t"]) if record else None

    return {"sigle": sigle, "prerequisites": prerequisites}


@router.get("/{sigle}", response_model=Cours)
def get_course(sigle: str):
    with get_driver().session() as session:
        record = session.run(
            "MATCH (c:Cours {sigle: $sigle}) RETURN c",
            sigle=sigle,
        ).single()

    if record is None:
        raise HTTPException(status_code=404, detail=f"Course '{sigle}' not found")

    return dict(record["c"])
