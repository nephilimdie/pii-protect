from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


@pytest.mark.asyncio
async def test_readiness_requires_database_migrations_and_detector(monkeypatch):
    monkeypatch.setattr(PresidioDetector, "_analyzer", object())
    monkeypatch.setattr(PrivacyFilterDetector, "_session", None)
    monkeypatch.setattr(PrivacyFilterDetector, "_tokenizer", None)

    result = await health.readiness(ReadySession())

    assert result == {
        "status": "ready",
        "checks": {"database": True, "migrations": True, "detector": True},
    }


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
