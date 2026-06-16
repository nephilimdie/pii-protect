import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
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
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("DELETE FROM domain_policies WHERE domain = :d"), {"d": domain}
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "not_found")
