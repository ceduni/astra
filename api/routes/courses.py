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
    credits: Optional[int]
    niveau: int
    hors_perimetre: bool
    description: str
    requirement_text: str


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


def _prereq_satisfied(node_ref, completed: set, groups: dict) -> bool:
    kind, val = node_ref
    if kind == "course":
        return val in completed
    group = groups[val]
    check = all if group["type"] == "AND" else any
    return check(_prereq_satisfied(item, completed, groups) for item in group["items"])


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

@router.post("/eligible", response_model=List[Cours])
def get_eligible(body: EligibilityRequest):
    completed = set(body.completed)

    with get_driver().session() as session:
        course_rows = list(session.run("""
            MATCH (c:Cours {hors_perimetre: false})
            OPTIONAL MATCH (c)-[:REQUIERT]->(t)
            RETURN c, t
        """))
        pg_rows = list(session.run("""
            MATCH (g:PrerequisiteGroup)-[:INCLUDES]->(child)
            RETURN g.id AS gid, g.type AS gtype, child
        """))

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
        else:
            if _prereq_satisfied(("group", t["id"]), completed, groups):
                eligible.append(dict(c))

    eligible.sort(key=lambda c: (c["universite"], c["sigle"]))
    return eligible


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
