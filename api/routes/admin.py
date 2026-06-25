"""
Admin endpoints for managing EQUIVAUT_A equivalences.

Protected by HTTP Basic auth. Credentials are read from the environment:
  ADMIN_USER     (default: admin)
  ADMIN_PASSWORD (default: astra-admin)

Endpoints
---------
POST   /admin/equivalences            create an equivalence
GET    /admin/equivalences            list with filters
PATCH  /admin/equivalences/{id}       re-activate a revoked equivalence
DELETE /admin/equivalences/{id}       soft-delete (status -> 'revoked')
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, model_validator

from ..database import get_driver

_http_basic = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_http_basic)) -> str:
    expected_user = os.environ.get("ADMIN_USER", "admin").encode()
    expected_pass = os.environ.get("ADMIN_PASSWORD", "astra-admin").encode()
    ok = (
        secrets.compare_digest(credentials.username.encode(), expected_user)
        and secrets.compare_digest(credentials.password.encode(), expected_pass)
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


admin_router = APIRouter(
    prefix="/admin/equivalences",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ── Models ────────────────────────────────────────────────────────────────────

Source = Literal["inferred", "official", "request"]
Status = Literal["active", "revoked", "expired"]


class EquivalenceCreate(BaseModel):
    sigle_a: str
    sigle_b: str
    source: Source = "official"
    created_by: Optional[str] = "admin"
    approved_by: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence: Optional[str] = None
    session: Optional[str] = None
    request_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_source_requirements(self):
        if self.sigle_a == self.sigle_b:
            raise ValueError("sigle_a and sigle_b must differ")
        if self.source == "request" and not self.session:
            raise ValueError("session is required when source = 'request'")
        return self


class Equivalence(BaseModel):
    id: str
    sigle_a: str
    sigle_b: str
    source: Source
    status: Status
    created_at: str
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[str] = None
    session: Optional[str] = None
    request_id: Optional[str] = None
    revoked_at: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_equivalence(record) -> Equivalence:
    r = record["r"]
    return Equivalence(
        id=r["id"],
        sigle_a=record["a"]["sigle"],
        sigle_b=record["b"]["sigle"],
        source=r["source"],
        status=r["status"],
        created_at=str(r["created_at"]),
        created_by=r.get("created_by"),
        approved_by=r.get("approved_by"),
        approved_at=str(r["approved_at"]) if r.get("approved_at") else None,
        confidence=r.get("confidence"),
        evidence=r.get("evidence"),
        session=r.get("session"),
        request_id=r.get("request_id"),
        revoked_at=str(r["revoked_at"]) if r.get("revoked_at") else None,
    )


def _assert_courses_exist(session, sigles: List[str]):
    rows = session.run(
        "MATCH (c:Cours) WHERE c.sigle IN $sigles RETURN c.sigle AS sigle",
        sigles=sigles,
    )
    found = {row["sigle"] for row in rows}
    missing = [s for s in sigles if s not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Course(s) not found: {', '.join(missing)}",
        )


# ── POST /admin/equivalences ──────────────────────────────────────────────────

@admin_router.post("", response_model=Equivalence, status_code=201)
def create_equivalence(body: EquivalenceCreate):
    edge_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    params = {
        "a": body.sigle_a,
        "b": body.sigle_b,
        "id": edge_id,
        "source": body.source,
        "status": "active",
        "created_at": now_iso,
        "created_by": body.created_by,
        "approved_by": body.approved_by,
        "approved_at": now_iso if body.approved_by else None,
        "confidence": body.confidence,
        "evidence": body.evidence,
        "session": body.session,
        "request_id": body.request_id,
    }

    with get_driver().session() as session:
        _assert_courses_exist(session, [body.sigle_a, body.sigle_b])

        record = session.run(
            """
            MATCH (a:Cours {sigle: $a}), (b:Cours {sigle: $b})
            CREATE (a)-[r:EQUIVAUT_A {
                id:          $id,
                source:      $source,
                status:      $status,
                created_at:  datetime($created_at),
                created_by:  $created_by,
                approved_by: $approved_by,
                approved_at: CASE WHEN $approved_at IS NULL
                                  THEN NULL ELSE datetime($approved_at) END,
                confidence:  $confidence,
                evidence:    $evidence,
                session:     $session,
                request_id:  $request_id
            }]->(b)
            RETURN r, a, b
            """,
            **params,
        ).single()

    return _row_to_equivalence(record)


# ── GET /admin/equivalences ───────────────────────────────────────────────────

@admin_router.get("", response_model=List[Equivalence])
def list_equivalences(
    source: Optional[Source] = None,
    status: Optional[Status] = None,
    sigle: Optional[str] = Query(
        None, description="Match either endpoint of the equivalence"
    ),
    universite: Optional[str] = Query(
        None, description="Match either endpoint's universite"
    ),
    limit: int = Query(100, ge=1, le=1000),
):
    filters = []
    params: dict = {"limit": limit}

    if source is not None:
        filters.append("r.source = $source")
        params["source"] = source
    if status is not None:
        filters.append("r.status = $status")
        params["status"] = status
    if sigle is not None:
        filters.append("(a.sigle = $sigle OR b.sigle = $sigle)")
        params["sigle"] = sigle
    if universite is not None:
        filters.append("(a.universite = $uni OR b.universite = $uni)")
        params["uni"] = universite

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with get_driver().session() as session:
        rows = list(session.run(
            f"""
            MATCH (a:Cours)-[r:EQUIVAUT_A]->(b:Cours)
            {where}
            RETURN r, a, b
            ORDER BY r.created_at DESC
            LIMIT $limit
            """,
            **params,
        ))

    return [_row_to_equivalence(row) for row in rows]


# ── PATCH /admin/equivalences/{id} ────────────────────────────────────────────

@admin_router.patch("/{equivalence_id}/restore", response_model=Equivalence)
def restore_equivalence(equivalence_id: str):
    with get_driver().session() as session:
        record = session.run(
            """
            MATCH (a:Cours)-[r:EQUIVAUT_A {id: $id}]->(b:Cours)
            SET r.status     = 'active',
                r.revoked_at = NULL
            RETURN r, a, b
            """,
            id=equivalence_id,
        ).single()

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Equivalence '{equivalence_id}' not found",
        )
    return _row_to_equivalence(record)


# ── DELETE /admin/equivalences/{id} ───────────────────────────────────────────

@admin_router.delete("/{equivalence_id}", response_model=Equivalence)
def revoke_equivalence(equivalence_id: str):
    with get_driver().session() as session:
        record = session.run(
            """
            MATCH (a:Cours)-[r:EQUIVAUT_A {id: $id}]->(b:Cours)
            SET r.status     = 'revoked',
                r.revoked_at = datetime()
            RETURN r, a, b
            """,
            id=equivalence_id,
        ).single()

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Equivalence '{equivalence_id}' not found",
        )
    return _row_to_equivalence(record)
