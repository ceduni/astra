from typing import Optional

from fastapi import APIRouter, Depends
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
