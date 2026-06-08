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
    protect_types: list[str]
    keep_types: list[str]
    surrogate_types: list[str]
    description: str | None
    enabled: bool
    updated_at: datetime


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


@router.get("/domain-policies", response_model=list[PolicyResponse])
async def list_policies(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text(
        "SELECT domain, protect_types, keep_types, surrogate_types, description, enabled, updated_at"
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
            "INSERT INTO domain_policies (domain, protect_types, keep_types, surrogate_types, description, enabled, updated_at)"
            " VALUES (:domain, CAST(:protect AS jsonb), CAST(:keep AS jsonb), CAST(:surrogate AS jsonb), :desc, :enabled, now())"
            " ON CONFLICT (domain) DO UPDATE SET"
            "   protect_types   = CAST(:protect AS jsonb),"
            "   keep_types      = CAST(:keep AS jsonb),"
            "   surrogate_types = CAST(:surrogate AS jsonb),"
            "   description     = :desc,"
            "   enabled         = :enabled,"
            "   updated_at      = now()"
            " RETURNING domain, protect_types, keep_types, surrogate_types, description, enabled, updated_at"
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
    await db.commit()
    return _row(result.fetchone()._mapping)


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
