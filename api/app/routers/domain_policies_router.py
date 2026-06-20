from __future__ import annotations
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.audit.audit_service import AuditService
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey

router = APIRouter()


class PolicyResponse(BaseModel):
    domain: str
    version: int
    protect_types: list[str]
    keep_types: list[str]
    surrogate_types: list[str]
    description: str | None
    enabled: bool
    updated_at: datetime


class PolicyVersionResponse(BaseModel):
    domain: str
    version: int
    snapshot: dict
    created_at: datetime


class UpsertPolicyRequest(BaseModel):
    protect_types: list[str]
    keep_types: list[str]
    surrogate_types: list[str] = []
    description: str | None = None
    enabled: bool = True


def _row(mapping) -> dict:
    d = dict(mapping)
    for k in ("protect_types", "keep_types", "surrogate_types"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
        elif d.get(k) is None:
            d[k] = []
    return d


def _history_row(mapping) -> dict:
    return {
        "domain": mapping["domain"],
        "version": mapping["version"],
        "snapshot": dict(mapping["snapshot"]),
        "created_at": mapping["created_at"],
    }


def _hash_payload(payload: dict | str) -> str:
    if isinstance(payload, str):
        value = payload
    else:
        value = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/domain-policies", response_model=list[PolicyResponse])
async def list_policies(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text(
        "SELECT domain, version, protect_types, keep_types, surrogate_types, description, enabled, updated_at"
        " FROM domain_policies ORDER BY domain"
    ))
    return [_row(r._mapping) for r in result.fetchall()]


@router.put("/domain-policies/{domain}", response_model=PolicyResponse)
async def upsert_policy(
    domain: str,
    body: UpsertPolicyRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            "INSERT INTO domain_policies (domain, version, protect_types, keep_types, surrogate_types, description, enabled, updated_at)"
            " VALUES (:domain, 1, CAST(:protect AS jsonb), CAST(:keep AS jsonb), CAST(:surrogate AS jsonb), :desc, :enabled, now())"
            " ON CONFLICT (domain) DO UPDATE SET"
            "   version         = domain_policies.version + 1,"
            "   protect_types   = CAST(:protect AS jsonb),"
            "   keep_types      = CAST(:keep AS jsonb),"
            "   surrogate_types = CAST(:surrogate AS jsonb),"
            "   description     = :desc,"
            "   enabled         = :enabled,"
            "   updated_at      = now()"
            " RETURNING domain, version, protect_types, keep_types, surrogate_types, description, enabled, updated_at"
        ),
        {
            "domain": domain,
            "protect":   json.dumps(body.protect_types),
            "keep":      json.dumps(body.keep_types),
            "surrogate": json.dumps(body.surrogate_types),
            "desc":      body.description,
            "enabled":   body.enabled,
        },
    )
    row = _row(result.fetchone()._mapping)
    await db.execute(
        text(
            "INSERT INTO domain_policy_versions (domain, version, snapshot)"
            " VALUES (:domain, :version, CAST(:snapshot AS jsonb))"
            " ON CONFLICT (domain, version) DO NOTHING"
        ),
        {"domain": row["domain"], "version": row["version"], "snapshot": json.dumps(row, default=str)},
    )
    await db.commit()
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="policy_update",
        context_id=domain,
        tenant_id=api_key.tenant_id,
        event_category="policy",
        document_hash=_hash_payload(row),
        ip=_client_ip(request),
    )
    return row


@router.get("/domain-policies/{domain}/versions", response_model=list[PolicyVersionResponse])
async def list_policy_versions(
    domain: str,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            "SELECT domain, version, snapshot, created_at"
            " FROM domain_policy_versions WHERE domain = :domain ORDER BY version DESC"
        ),
        {"domain": domain},
    )
    return [_history_row(row._mapping) for row in result.fetchall()]


@router.delete("/domain-policies/{domain}", status_code=204)
async def delete_policy(
    domain: str,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("DELETE FROM domain_policies WHERE domain = :d"), {"d": domain}
    )
    if result.rowcount == 0:
        await db.rollback()
        raise HTTPException(404, "not_found")
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="policy_delete",
        context_id=domain,
        tenant_id=api_key.tenant_id,
        event_category="policy",
        document_hash=_hash_payload(domain),
        ip=_client_ip(request),
    )
