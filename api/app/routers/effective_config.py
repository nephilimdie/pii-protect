"""Effective runtime configuration preview for an administrator."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.detection.config_resolver import DetectionConfigResolver
from app.detection.layer_settings_repository import LayerSettingsRepository
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.surrogates.policy_service import PolicyService

router = APIRouter()


def _active_layers(app_state, enabled_layers: set[str] | None) -> list[str]:
    if enabled_layers is not None:
        return sorted(enabled_layers)
    return sorted(
        str(row.get("code"))
        for row in getattr(app_state, "detection_layers_raw", [])
        if row.get("enabled", True) and row.get("code")
    )


def _policy_preview(policy: dict) -> dict:
    return {
        "id": policy.get("policy_id"),
        "version": policy.get("policy_version"),
        "hash": policy.get("policy_hash"),
        "mode": policy.get("mode"),
        "detection_layers": policy.get("detection_layers"),
        "protect_types": sorted(policy["protect_types"]) if policy.get("protect_types") is not None else None,
        "keep_types": sorted(policy.get("keep_types", [])),
        "surrogate_types": sorted(policy.get("surrogate_types", [])),
        "remove_types": sorted(policy.get("remove_types", [])),
        "block_types": sorted(policy.get("block_types", [])),
        "confidence_thresholds": policy.get("confidence_thresholds", {}),
        "allowlist_type_count": len(policy.get("allowlist", {})),
    }


@router.get("/effective-config")
async def effective_config(
    request: Request,
    context_type: str | None = Query(None, max_length=100),
    domain: str | None = Query(None, max_length=100),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the effective policy and detector settings for a request preview."""
    cfg = await DetectionConfigResolver(db, api_key.tenant_id).resolve(
        request.app.state
    )
    layer_settings = await LayerSettingsRepository(db).get_effective(api_key.tenant_id)
    policy = await PolicyService(db, tenant_id=api_key.tenant_id).resolve(
        context_type=context_type,
        domain=domain,
    )

    return {
        "tenant_id": api_key.tenant_id,
        "context_type": context_type,
        "domain": domain,
        "policy": _policy_preview(policy),
        "detection": {
            "active_layers": _active_layers(request.app.state, cfg.enabled_layers),
            "layer_settings": layer_settings,
            "regex_pattern_count": len(cfg.regex_patterns),
            "denylist_type_count": len(cfg.denylist),
            "context_entity_type_count": len(cfg.presidio_context),
            "reclassification_rule_count": len(cfg.reclassification_rules),
        },
    }
