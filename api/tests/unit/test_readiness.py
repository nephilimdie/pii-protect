from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import settings
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.routers import health


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ReadySession:
    async def execute(self, query):
        if "SELECT 1" in str(query):
            return Result(1)
        return Result("054")


ALL_ENABLED = {
    "presidio": {"enabled": True},
    "privacy_filter": {"enabled": True},
    "ai4privacy": {"enabled": True},
    "regex": {"enabled": True},
}


def _load_layers(monkeypatch, presidio=True, privacy_filter=True, ai4privacy=True, layers=ALL_ENABLED):
    monkeypatch.setattr(settings, "detection_layers", layers)
    monkeypatch.setattr(PresidioDetector, "_analyzer", object() if presidio else None)
    monkeypatch.setattr(PrivacyFilterDetector, "_session", object() if privacy_filter else None)
    monkeypatch.setattr(PrivacyFilterDetector, "_tokenizer", object() if privacy_filter else None)
    monkeypatch.setattr(Ai4PrivacyDetector, "_pipeline", object() if ai4privacy else None)


@pytest.mark.asyncio
async def test_readiness_ready_when_every_enabled_layer_is_loaded(monkeypatch):
    _load_layers(monkeypatch)

    result = await health.readiness(ReadySession())

    assert result == {
        "status": "ready",
        "checks": {
            "database": True,
            "migrations": True,
            "detector": True,
            "detector_layers": {"presidio": True, "privacy_filter": True, "ai4privacy": True},
        },
    }


@pytest.mark.asyncio
async def test_readiness_fails_closed_when_an_enabled_layer_failed_to_load(monkeypatch):
    # Regression: preshed 3.0.14 broke spaCy, Presidio failed to load and CREDIT_CARD vanished
    # while the other ML layers kept readiness green.
    _load_layers(monkeypatch, presidio=False)

    with pytest.raises(HTTPException) as error:
        await health.readiness(ReadySession())

    assert error.value.status_code == 503
    assert error.value.detail["checks"]["detector"] is False
    assert error.value.detail["checks"]["detector_layers"] == {
        "presidio": False, "privacy_filter": True, "ai4privacy": True,
    }


@pytest.mark.asyncio
async def test_readiness_ignores_disabled_layers(monkeypatch):
    layers = {**ALL_ENABLED, "ai4privacy": {"enabled": False}}
    _load_layers(monkeypatch, ai4privacy=False, layers=layers)

    result = await health.readiness(ReadySession())

    assert result["checks"]["detector_layers"] == {"presidio": True, "privacy_filter": True}


@pytest.mark.asyncio
async def test_health_reports_models_loaded_when_any_layer_loaded(monkeypatch):
    _load_layers(monkeypatch, presidio=False, privacy_filter=False)

    assert (await health.health())["models_loaded"] is True


@pytest.mark.asyncio
async def test_readiness_returns_not_ready_when_database_is_unavailable():
    class BrokenSession:
        async def execute(self, _query):
            raise RuntimeError("database_down")

    with pytest.raises(HTTPException) as error:
        await health.readiness(BrokenSession())

    assert error.value.status_code == 503
    assert error.value.detail["checks"] == {
        "database": False,
        "migrations": False,
        "detector": False,
    }
