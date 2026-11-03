from fastapi import HTTPException

from app.config import settings
from app.detection.layer_config import LAYER_META


def validate_layer_override(code: str, action: str, data: dict) -> None:
    if code not in LAYER_META or action == "custom":
        raise HTTPException(status_code=422, detail="unknown_detection_layer")
    if action == "hidden":
        return
    if "enabled" in data and not isinstance(data["enabled"], bool):
        raise HTTPException(status_code=422, detail="invalid_layer_enabled")
    if data.get("enabled") and not settings.layer_enabled(code):
        raise HTTPException(status_code=409, detail="detection_layer_requires_platform_activation")
    levels = data.get("protection_levels")
    if levels is not None and (
        not isinstance(levels, list)
        or any(not isinstance(level, str) or level not in {"balanced", "maximum"} for level in levels)
    ):
        raise HTTPException(status_code=422, detail="invalid_protection_levels")
