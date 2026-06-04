from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.api_key_service import ApiKeyService
from app.identity.models import ApiKey


async def get_api_key(
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="missing_api_key")
    service = ApiKeyService(db)
    api_key = await service.verify(x_api_key)
    if api_key is None:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    return api_key


async def require_service(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role not in ("service", "admin"):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key


async def require_admin(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role != "admin":
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key


async def require_auditor(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role not in ("auditor", "admin"):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key
