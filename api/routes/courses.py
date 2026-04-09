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
