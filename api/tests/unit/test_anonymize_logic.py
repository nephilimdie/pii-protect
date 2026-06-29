"""Unit tests for shared helpers in _anonymize_logic."""

from __future__ import annotations

import os
import sys
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-chars-padded-00000000")
os.environ.setdefault("ADMIN_INITIAL_KEY", "test-admin-key")

from sqlalchemy.orm import DeclarativeBase

_database_stub = ModuleType("app.database")


class _Base(DeclarativeBase):
    pass


async def _get_db():
    yield None


_database_stub.Base = _Base
_database_stub.get_db = _get_db
sys.modules["app.database"] = _database_stub

from app.detection.entities import PiiEntity
from app.routers._anonymize_logic import filter_detected_entities


def _entity(pii_type: str, text: str = "x", start: int = 0, end: int = 1) -> PiiEntity:
    return PiiEntity(start=start, end=end, pii_type=pii_type, text=text, score=0.9)


class TestFilterDetectedEntities:
    def test_no_filters_returns_all(self):
        entities = [_entity("EMAIL"), _entity("PHONE"), _entity("FISCAL_CODE")]
        result = filter_detected_entities(entities)
        assert result == entities

    def test_keep_removes_specified_types(self):
        entities = [_entity("EMAIL"), _entity("PHONE"), _entity("FISCAL_CODE")]
        result = filter_detected_entities(entities, keep_types={"EMAIL", "PHONE"})
        assert len(result) == 1
        assert result[0].pii_type == "FISCAL_CODE"

    def test_protect_keeps_only_specified_types(self):
        entities = [_entity("EMAIL"), _entity("PHONE"), _entity("FISCAL_CODE")]
        result = filter_detected_entities(entities, protect_types={"EMAIL"})
        assert len(result) == 1
        assert result[0].pii_type == "EMAIL"

    def test_always_include_bypasses_protect(self):
        entities = [_entity("EMAIL"), _entity("PHONE"), _entity("FISCAL_CODE")]
        result = filter_detected_entities(
            entities,
            protect_types={"EMAIL"},
            always_include_types={"FISCAL_CODE"},
        )
        types = {e.pii_type for e in result}
        assert types == {"EMAIL", "FISCAL_CODE"}
        assert "PHONE" not in types

    def test_keep_wins_over_always_include(self):
        entities = [_entity("EMAIL"), _entity("FISCAL_CODE")]
        result = filter_detected_entities(
            entities,
            keep_types={"FISCAL_CODE"},
            always_include_types={"FISCAL_CODE"},
        )
        assert len(result) == 1
        assert result[0].pii_type == "EMAIL"

    def test_empty_entities(self):
        assert filter_detected_entities([]) == []

    def test_protect_none_means_no_type_filter(self):
        entities = [_entity("EMAIL"), _entity("PHONE")]
        result = filter_detected_entities(entities, protect_types=None)
        assert len(result) == 2

    def test_protect_empty_set_blocks_all(self):
        entities = [_entity("EMAIL"), _entity("PHONE")]
        result = filter_detected_entities(entities, protect_types=set())
        assert result == []

    def test_always_include_without_protect_has_no_effect(self):
        entities = [_entity("EMAIL"), _entity("PHONE")]
        result = filter_detected_entities(entities, always_include_types={"FISCAL_CODE"})
        assert len(result) == 2
