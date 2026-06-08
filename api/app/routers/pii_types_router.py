from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey

router = APIRouter()


class PiiTypeResponse(BaseModel):
    code: str
    category: str
    display_name: str
    default_action: str
    faker_strategy: str | None
    reversible: bool
    enabled: bool
    description: str | None


class UpdatePiiTypeRequest(BaseModel):
    display_name: str | None = None
    default_action: str | None = None
    faker_strategy: str | None = None
    reversible: bool | None = None
    enabled: bool | None = None
    description: str | None = None


@router.get("/pii-types", response_model=list[PiiTypeResponse])
async def list_types(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text(
        "SELECT code, category, display_name, default_action, faker_strategy, reversible, enabled, description"
        " FROM pii_type_registry ORDER BY category, code"
    ))
    return [dict(r._mapping) for r in result.fetchall()]


@router.put("/pii-types/{code}", response_model=PiiTypeResponse)
async def update_type(
    code: str,
    body: UpdatePiiTypeRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    result = await db.execute(
        text(f"UPDATE pii_type_registry SET {sets} WHERE code = :code"
             " RETURNING code, category, display_name, default_action, faker_strategy, reversible, enabled, description"),
        {"code": code, **updates},
    )
    await db.commit()
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "not_found")
    return dict(row._mapping)
