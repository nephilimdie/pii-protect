from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.anonymization.anonymizer import PiiAnonymizer
from app.detection.detector_registry import DetectorRegistry
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.routers import _anonymize_logic as module
from app.routers._anonymize_models import AnonymizeRequest


@pytest.mark.asyncio
async def test_real_detector_failure_reaches_router_as_503_without_original(monkeypatch):
    layer = Ai4PrivacyDetector()
    layer._pipeline = Mock(side_effect=RuntimeError('inference unavailable'))
    registry = DetectorRegistry()
    registry.register(layer)
    anonymizer = PiiAnonymizer(registry)
    policy = dict(protect_types=None, keep_types=[], surrogate_types=[], remove_types=[],
                  block_types=[], confidence_thresholds={}, allowlist={}, mode='tag')
    monkeypatch.setattr(module, 'UsageService', lambda db: SimpleNamespace(
        ensure_within_limits=AsyncMock(), record=AsyncMock()))
    monkeypatch.setattr(module, 'PolicyService', lambda *args, **kwargs: SimpleNamespace(
        resolve=AsyncMock(return_value=policy)))
    monkeypatch.setattr(module.settings, 'failure_mode', 'closed')
    original = 'private.person@example.org'
    with pytest.raises(HTTPException) as failure:
        await module._process_anonymization(
            AnonymizeRequest(text=original, context_id='fault-test'),
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
            SimpleNamespace(id='test-key', role='admin'), None, anonymizer,
        )
    assert failure.value.status_code == 503
    assert failure.value.detail['safe'] is False
    assert original not in str(failure.value.detail)
