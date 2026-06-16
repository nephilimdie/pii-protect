from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey

router = APIRouter()


class ContextTypeResponse(BaseModel):
    code: str
    display_name: str
    domain: str | None
    default_mode: str
    description: str | None
    enabled: bool
    version: int
    created_at: datetime


class ContextTypeVersionResponse(BaseModel):
    code: str
    version: int
    snapshot: dict
    created_at: datetime


def _history_row(mapping) -> dict:
    return {
        "code": mapping["code"],
        "version": mapping["version"],
        "snapshot": dict(mapping["snapshot"]),
        "created_at": mapping["created_at"],
    }


class CreateContextTypeRequest(BaseModel):
    code: str
    display_name: str
    domain: str | None = None
    default_mode: str = "tag"
    description: str | None = None


class UpdateContextTypeRequest(BaseModel):
    display_name: str | None = None
    domain: str | None = None
    default_mode: str | None = None
    description: str | None = None
    enabled: bool | None = None


@router.get("/context-types", response_model=list[ContextTypeResponse])
async def list_context_types(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text(
        "SELECT code, display_name, domain, default_mode, description, enabled, version, created_at"
        " FROM context_types ORDER BY code"
    ))
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/context-types", response_model=ContextTypeResponse, status_code=201)
async def create_context_type(
    body: CreateContextTypeRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            "INSERT INTO context_types (code, display_name, domain, default_mode, description, version)"
            " VALUES (:code, :display_name, :domain, :mode, :desc, 1)"
            " ON CONFLICT (code) DO NOTHING"
            " RETURNING code, display_name, domain, default_mode, description, enabled, version, created_at"
        ),
        {"code": body.code, "display_name": body.display_name,
         "domain": body.domain, "mode": body.default_mode, "desc": body.description},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(409, "code_already_exists")
    payload = dict(row._mapping)
    await db.execute(
        text(
            "INSERT INTO context_type_versions (code, version, snapshot)"
            " VALUES (:code, :version, CAST(:snapshot AS jsonb))"
            " ON CONFLICT (code, version) DO NOTHING"
        ),
        {"code": payload["code"], "version": payload["version"], "snapshot": json.dumps(payload, default=str)},
    )
    await db.commit()
    return payload


@router.put("/context-types/{code}", response_model=ContextTypeResponse)
async def update_context_type(
    code: str,
    body: UpdateContextTypeRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "no_fields")
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    result = await db.execute(
           text(f"UPDATE context_types SET {sets}, version = version + 1 WHERE code = :code"
               " RETURNING code, display_name, domain, default_mode, description, enabled, version, created_at"),
        {"code": code, **updates},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "not_found")
    payload = dict(row._mapping)
    await db.execute(
        text(
            "INSERT INTO context_type_versions (code, version, snapshot)"
            " VALUES (:code, :version, CAST(:snapshot AS jsonb))"
            " ON CONFLICT (code, version) DO NOTHING"
        ),
        {"code": payload["code"], "version": payload["version"], "snapshot": json.dumps(payload, default=str)},
    )
    await db.commit()
    return payload


@router.get("/context-types/{code}/versions", response_model=list[ContextTypeVersionResponse])
async def list_context_type_versions(
    code: str,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            "SELECT code, version, snapshot, created_at"
            " FROM context_type_versions WHERE code = :code ORDER BY version DESC"
        ),
        {"code": code},
    )
    return [_history_row(row._mapping) for row in result.fetchall()]


@router.delete("/context-types/{code}", status_code=204)
async def delete_context_type(
    code: str,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("DELETE FROM context_types WHERE code = :c"), {"c": code}
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "not_found")
