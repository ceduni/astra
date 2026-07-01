"""
Admin endpoints for managing EQUIVAUT_A equivalences.

Protected by HTTP Basic auth. Credentials are read from the environment:

  Primary (multi-account):
    ADMIN_ACCOUNTS  JSON array of {username, password, university}
                    e.g. '[{"username":"admin_udem","password":"s3cr3t","university":"UdeM"}]'

  Fallback (legacy single-account):
    ADMIN_USER        (default: admin)
    ADMIN_PASSWORD    (default: astra-admin)
    ADMIN_UNIVERSITY  (optional) university scope

Endpoints
---------
GET    /admin/me                        current admin identity + university scope
POST   /admin/equivalences              create an equivalence (source: admin_created)
GET    /admin/equivalences              list with filters (scoped to admin's university)
GET    /admin/equivalences/me           alias for /admin/me
GET    /admin/equivalences/pending      inferred equivalences awaiting review
PATCH  /admin/equivalences/{id}/approve approve a pending equivalence
PATCH  /admin/equivalences/{id}/skip    pass without explicit approval
PATCH  /admin/equivalences/{id}/reject  revoke an equivalence
PATCH  /admin/equivalences/{id}/restore re-activate a revoked equivalence
DELETE /admin/equivalences/{id}         soft-delete (status -> 'revoked')
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, model_validator

from ..database import get_driver

_http_basic = HTTPBasic()


@dataclass
class AdminContext:
    username: str
    university: str | None


def _parse_accounts() -> list[dict] | None:
    raw = os.environ.get("ADMIN_ACCOUNTS", "").strip()
    if not raw:
        return None
    try:
        accounts = json.loads(raw)
        if isinstance(accounts, list) and accounts:
            return accounts
    except json.JSONDecodeError:
        pass
    return None


def require_admin(credentials: HTTPBasicCredentials = Depends(_http_basic)) -> AdminContext:
    # TODO: replace plaintext password comparison with bcrypt hashing before production
    given_user = credentials.username.encode()
    given_pass = credentials.password.encode()

    accounts = _parse_accounts()
    if accounts is not None:
        # Multi-account mode: check against ADMIN_ACCOUNTS list.
        # Always iterate all accounts to avoid timing-based username enumeration.
        matched: dict | None = None
        for account in accounts:
            user_ok = secrets.compare_digest(given_user, account.get("username", "").encode())
            pass_ok = secrets.compare_digest(given_pass, account.get("password", "").encode())
            if user_ok and pass_ok:
                matched = account
        if matched is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return AdminContext(
            username=matched["username"],
            university=matched.get("university") or None,
        )

    # Legacy single-account fallback
    expected_user = os.environ.get("ADMIN_USER", "admin").encode()
    expected_pass = os.environ.get("ADMIN_PASSWORD", "astra-admin").encode()
    ok = (
        secrets.compare_digest(given_user, expected_user)
        and secrets.compare_digest(given_pass, expected_pass)
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return AdminContext(
        username=credentials.username,
        university=os.environ.get("ADMIN_UNIVERSITY") or None,
    )


# ── Meta router: /admin ────────────────────────────────────────────────────────

admin_meta_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_meta_router.get("/me")
def admin_me(ctx: AdminContext = Depends(require_admin)):
    return {"username": ctx.username, "university": ctx.university}


# ── Equivalences router: /admin/equivalences ──────────────────────────────────

admin_router = APIRouter(
    prefix="/admin/equivalences",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ── Models ────────────────────────────────────────────────────────────────────

Source = Literal["inferred", "official", "official_table", "admin_created", "request"]
Status = Literal["active", "pending", "needs_review", "revoked", "expired"]


class EquivalenceCreate(BaseModel):
    sigle_a: str
    sigle_b: str
    source: Source = "admin_created"
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence: Optional[str] = None
    session: Optional[str] = None
    request_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_requirements(self):
        if self.sigle_a == self.sigle_b:
            raise ValueError("sigle_a and sigle_b must differ")
        if self.source == "admin_created" and not (self.evidence or "").strip():
            raise ValueError("evidence (justification) is required when source = 'admin_created'")
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
    flagged_at: Optional[str] = None
    flag_reason: Optional[str] = None


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
        flagged_at=str(r["flagged_at"]) if r.get("flagged_at") else None,
        flag_reason=r.get("flag_reason"),
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


# ── GET /admin/equivalences/me ────────────────────────────────────────────────
# Must be defined before parameterised routes to avoid path conflict.

@admin_router.get("/me")
def admin_me_alias(ctx: AdminContext = Depends(require_admin)):
    return {"username": ctx.username, "university": ctx.university}


# ── GET /admin/equivalences/pending ──────────────────────────────────────────

@admin_router.get("/pending", response_model=List[Equivalence])
def list_pending(
    ctx: AdminContext = Depends(require_admin),
    limit: int = Query(200, ge=1, le=1000),
):
    filters = ["r.source = 'inferred'", "r.status IN ['pending', 'needs_review']"]
    params: dict = {"limit": limit}

    if ctx.university:
        filters.append("(a.universite = $uni OR b.universite = $uni)")
        params["uni"] = ctx.university

    where = "WHERE " + " AND ".join(filters)

    with get_driver().session() as session:
        rows = list(session.run(
            f"""
            MATCH (a:Cours)-[r:EQUIVAUT_A]->(b:Cours)
            {where}
            RETURN r, a, b
            ORDER BY r.confidence DESC
            LIMIT $limit
            """,
            **params,
        ))
    return [_row_to_equivalence(row) for row in rows]


# ── POST /admin/equivalences ──────────────────────────────────────────────────

@admin_router.post("", response_model=Equivalence, status_code=201)
def create_equivalence(body: EquivalenceCreate, ctx: AdminContext = Depends(require_admin)):
    edge_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    params = {
        "a": body.sigle_a,
        "b": body.sigle_b,
        "id": edge_id,
        "source": body.source,
        "status": "active",
        "created_at": now_iso,
        "created_by": ctx.username,
        "approved_by": ctx.username,
        "approved_at": now_iso,
        "confidence": body.confidence if body.confidence is not None else 1.0,
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
                approved_at: datetime($approved_at),
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
    ctx: AdminContext = Depends(require_admin),
    source: Optional[Source] = None,
    status: Optional[Status] = None,
    sigle: Optional[str] = Query(None, description="Match either endpoint of the equivalence"),
    universite: Optional[str] = Query(None, description="Match either endpoint's universite"),
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

    effective_uni = universite or ctx.university
    if effective_uni is not None:
        filters.append("(a.universite = $uni OR b.universite = $uni)")
        params["uni"] = effective_uni

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


# ── PATCH /admin/equivalences/{id}/approve ────────────────────────────────────

@admin_router.patch("/{equivalence_id}/approve", response_model=Equivalence)
def approve_equivalence(equivalence_id: str, ctx: AdminContext = Depends(require_admin)):
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_driver().session() as session:
        record = session.run(
            """
            MATCH (a:Cours)-[r:EQUIVAUT_A {id: $id}]->(b:Cours)
            SET r.status      = 'active',
                r.approved_by = $admin,
                r.approved_at = datetime($now),
                r.flagged_at  = NULL,
                r.flag_reason = NULL
            RETURN r, a, b
            """,
            id=equivalence_id, admin=ctx.username, now=now_iso,
        ).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Equivalence '{equivalence_id}' not found")
    return _row_to_equivalence(record)


# ── PATCH /admin/equivalences/{id}/skip ───────────────────────────────────────

@admin_router.patch("/{equivalence_id}/skip", response_model=Equivalence)
def skip_equivalence(equivalence_id: str):
    with get_driver().session() as session:
        record = session.run(
            """
            MATCH (a:Cours)-[r:EQUIVAUT_A {id: $id}]->(b:Cours)
            SET r.status      = 'active',
                r.flagged_at  = NULL,
                r.flag_reason = NULL
            RETURN r, a, b
            """,
            id=equivalence_id,
        ).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Equivalence '{equivalence_id}' not found")
    return _row_to_equivalence(record)


# ── PATCH /admin/equivalences/{id}/reject ─────────────────────────────────────

@admin_router.patch("/{equivalence_id}/reject", response_model=Equivalence)
def reject_equivalence(equivalence_id: str):
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
        raise HTTPException(status_code=404, detail=f"Equivalence '{equivalence_id}' not found")
    return _row_to_equivalence(record)


# ── PATCH /admin/equivalences/{id}/restore ────────────────────────────────────

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
