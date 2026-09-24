from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.identity.models import ApiKey
from app.routers import effective_config


def _request() -> Request:
    scope = {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(
        detection_layers_raw=[
            {"code": "regex", "enabled": True},
            {"code": "presidio", "enabled": True},
            {"code": "ai4privacy", "enabled": False},
        ],
    ))}
    return Request(scope)


@pytest.mark.asyncio
async def test_effective_config_returns_safe_runtime_preview(monkeypatch):
    config = SimpleNamespace(
        enabled_layers={"regex", "presidio"},
        regex_patterns=[{"id": "secret-pattern", "pattern": "DO_NOT_RETURN"}],
        denylist={"PERSON": {"exact": {"Alice"}}},
        presidio_context={"PERSON": ["employee"]},
        reclassification_rules=[{"id": "rule-1"}],
    )
    monkeypatch.setattr(
        effective_config.DetectionConfigResolver,
        "resolve",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        effective_config.LayerSettingsRepository,
        "get_effective",
        AsyncMock(return_value={"presidio": {"min_score": 0.8}}),
    )
    monkeypatch.setattr(
        effective_config.PolicyService,
        "resolve",
        AsyncMock(return_value={
            "policy_id": "fine_appeal",
            "policy_version": "context:2|domain:3",
            "policy_hash": "hash",
            "mode": "tag",
            "protect_types": {"EMAIL", "PERSON"},
            "keep_types": {"DATE"},
            "surrogate_types": set(),
            "remove_types": set(),
            "block_types": {"SECRET"},
            "confidence_thresholds": {"PERSON": 0.8},
            "allowlist": {"EMAIL": ["example.test"]},
        }),
    )

    result = await effective_config.effective_config(
        request=_request(),
        context_type="fine_appeal",
        domain=None,
        api_key=SimpleNamespace(tenant_id="tenant-a"),
        db=object(),
    )

    assert result["detection"]["active_layers"] == ["presidio", "regex"]
    assert result["detection"]["regex_pattern_count"] == 1
    assert result["policy"]["protect_types"] == ["EMAIL", "PERSON"]
    assert result["policy"]["allowlist_type_count"] == 1
    assert "DO_NOT_RETURN" not in str(result)
