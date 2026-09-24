from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector

router = APIRouter()


@router.get("/health")
async def health():
    models_loaded = (
        PresidioDetector._analyzer is not None
        or (PrivacyFilterDetector._session is not None and PrivacyFilterDetector._tokenizer is not None)
        or Ai4PrivacyDetector._pipeline is not None
    )
    return {"status": "ok", "version": "1.0.0", "models_loaded": models_loaded}


@router.get("/readiness")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Return 503 until the database, migrations and detector are usable."""
    checks = {"database": False, "migrations": False, "detector": False}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
        migration = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        checks["migrations"] = migration.scalar_one_or_none() is not None
    except Exception:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    checks["detector"] = (
        PresidioDetector._analyzer is not None
        or (PrivacyFilterDetector._session is not None and PrivacyFilterDetector._tokenizer is not None)
        or Ai4PrivacyDetector._pipeline is not None
    )
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
