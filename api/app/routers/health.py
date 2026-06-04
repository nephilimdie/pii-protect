from fastapi import APIRouter
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector

router = APIRouter()


@router.get("/health")
async def health():
    models_loaded = (
        PresidioDetector._analyzer is not None
        or PrivacyFilterDetector._pipeline is not None
    )
    return {"status": "ok", "version": "1.0.0", "models_loaded": models_loaded}
