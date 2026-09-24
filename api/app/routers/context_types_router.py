from __future__ import annotations
from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey

router = APIRouter()
KNOWN_DETECTION_LAYERS = {"regex", "presidio", "privacy_filter", "ai4privacy"}


class ContextTypeResponse(BaseModel):
    code: str
    display_name: str
    domain: str | None
    default_mode: str
    detection_layers: list[str] | None
    description: str | None
    visible_to_clients: list[str] | None
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
    detection_layers: list[str] | None = None
    description: str | None = None
    visible_to_clients: list[str] | None = None


class UpdateContextTypeRequest(BaseModel):
    display_name: str | None = None
    domain: str | None = None
    default_mode: str | None = None
    detection_layers: list[str] | None = None
    description: str | None = None
    visible_to_clients: list[str] | None = None
    enabled: bool | None = None


def _validate_layers(layers: list[str] | None) -> list[str] | None:
    if layers is None:
        return None
    normalized = list(dict.fromkeys(layers))
    unknown = sorted(set(normalized) - KNOWN_DETECTION_LAYERS)
    if unknown:
        raise HTTPException(422, {"error": "unknown_detection_layer", "layers": unknown})
    if not normalized:
        raise HTTPException(422, "detection_layers_must_not_be_empty")
    return normalized


@router.get("/context-types", response_model=list[ContextTypeResponse])
async def list_context_types(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text(
        "SELECT code, display_name, domain, default_mode, detection_layers, description, visible_to_clients, enabled, version, created_at"
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
            "INSERT INTO context_types (code, display_name, domain, default_mode, detection_layers, description, visible_to_clients, version)"
            " VALUES (:code, :display_name, :domain, :mode, CAST(:layers AS jsonb), :desc, CAST(:visible AS jsonb), 1)"
            " ON CONFLICT (code) DO NOTHING"
            " RETURNING code, display_name, domain, default_mode, detection_layers, description, visible_to_clients, enabled, version, created_at"
        ),
        {"code": body.code, "display_name": body.display_name,
         "domain": body.domain, "mode": body.default_mode, "desc": body.description,
         "visible": json.dumps(body.visible_to_clients) if body.visible_to_clients else None,
         "layers": json.dumps(_validate_layers(body.detection_layers)) if body.detection_layers is not None else None},
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

    # visible_to_clients is JSONB — cast it and serialise the value.
    params = {"code": code}
    set_clauses = []
    for k, v in updates.items():
        if k == "visible_to_clients":
            set_clauses.append("visible_to_clients = CAST(:visible_to_clients AS jsonb)")
            params["visible_to_clients"] = json.dumps(v)
        elif k == "detection_layers":
            set_clauses.append("detection_layers = CAST(:detection_layers AS jsonb)")
            params["detection_layers"] = json.dumps(_validate_layers(v))
        else:
            set_clauses.append(f"{k} = :{k}")
            params[k] = v
    sets = ", ".join(set_clauses)
    result = await db.execute(
           text(f"UPDATE context_types SET {sets}, version = version + 1 WHERE code = :code"
               " RETURNING code, display_name, domain, default_mode, detection_layers, description, visible_to_clients, enabled, version, created_at"),
        params,
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


@router.post("/context-types/{code}/versions/{version}/rollback", response_model=ContextTypeResponse)
async def rollback_context_type(
    code: str,
    version: int,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    history = await db.execute(
        text("SELECT snapshot FROM context_type_versions WHERE code = :code AND version = :version"),
        {"code": code, "version": version},
    )
    history_row = history.fetchone()
    if not history_row:
        raise HTTPException(404, "context_type_version_not_found")
    snapshot = dict(history_row._mapping["snapshot"])
    params = {
        "code": code,
        "display_name": snapshot.get("display_name") or code,
        "domain": snapshot.get("domain"),
        "mode": snapshot.get("default_mode") or "tag",
        "layers": json.dumps(_validate_layers(snapshot.get("detection_layers"))) if snapshot.get("detection_layers") is not None else None,
        "desc": snapshot.get("description"),
        "visible": json.dumps(snapshot.get("visible_to_clients")) if snapshot.get("visible_to_clients") else None,
        "enabled": snapshot.get("enabled", True),
    }
    result = await db.execute(text(
        "UPDATE context_types SET display_name = :display_name, domain = :domain, default_mode = :mode,"
        " detection_layers = CAST(:layers AS jsonb), description = :desc, visible_to_clients = CAST(:visible AS jsonb), enabled = :enabled, version = version + 1"
        " WHERE code = :code RETURNING code, display_name, domain, default_mode, description, visible_to_clients,"
        " detection_layers, enabled, version, created_at"
    ), params)
    row = result.fetchone()
    if not row:
        await db.rollback()
        raise HTTPException(404, "context_type_not_found")
    payload = dict(row._mapping)
    await db.execute(text(
        "INSERT INTO context_type_versions (code, version, snapshot)"
        " VALUES (:code, :version, CAST(:snapshot AS jsonb))"
        " ON CONFLICT (code, version) DO NOTHING"
    ), {"code": code, "version": payload["version"], "snapshot": json.dumps(payload, default=str)})
    await db.commit()
    return payload


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
