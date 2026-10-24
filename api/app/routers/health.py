from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector

router = APIRouter()

_ML_LAYERS: tuple[type[DetectorContract], ...] = (PresidioDetector, PrivacyFilterDetector, Ai4PrivacyDetector)


def _ml_layer_status(enabled_only: bool) -> dict[str, bool]:
    """Why: a layer that fails to preload only logs, so health probes must check each layer explicitly.
    What: maps layer_name -> loaded, optionally restricted to layers enabled in settings.
    Test: with PresidioDetector._analyzer=None and presidio enabled, result["presidio"] is False.
    """
    detectors = (cls() for cls in _ML_LAYERS)
    return {
        d.layer_name: d.is_available()
        for d in detectors
        if not enabled_only or settings.layer_enabled(d.layer_name)
    }


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "models_loaded": any(_ml_layer_status(enabled_only=False).values())}


@router.get("/readiness")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Why: a detector that silently fails to load drops whole entity types (e.g. CREDIT_CARD) while serving 200s.
    What: 503 unless the database, migrations and every enabled ML detector layer are usable.
    Test: set PresidioDetector._analyzer=None with presidio enabled; expect 503 and detector_layers.presidio False.
    """
    checks: dict[str, object] = {"database": False, "migrations": False, "detector": False}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
        migration = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        checks["migrations"] = migration.scalar_one_or_none() is not None
    except Exception:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    layers = _ml_layer_status(enabled_only=True)
    checks["detector"] = all(layers.values())
    checks["detector_layers"] = layers
    if not (checks["database"] and checks["migrations"] and checks["detector"]):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
