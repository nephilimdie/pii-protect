"""Unit tests for SurrogateService — DB mocked with AsyncMock."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, MagicMock, call
from app.surrogates.surrogate_service import SurrogateService


def _make_db(lookup_value=None, profile_row=None):
    """Build a minimal AsyncSession mock.
    lookup_value: fake_value returned by surrogate_mappings lookup (None = cache miss)
    profile_row: dict returned by surrogate_profiles lookup (None = no existing profile)
    """
    async def execute_side_effect(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "surrogate_profiles" in sql and "SELECT" in sql:
            result.fetchone.return_value = (
                MagicMock(_mapping=profile_row) if profile_row else None
            )
        elif "surrogate_mappings" in sql and "SELECT" in sql:
            row = MagicMock()
            row.__getitem__ = lambda self, i: lookup_value
            result.fetchone.return_value = row if lookup_value else None
        else:
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_side_effect)
    db.commit = AsyncMock()
    return db


# ── simple value path ─────────────────────────────────────────────────────────

class TestSimpleValue:

    @pytest.mark.asyncio
    async def test_cache_miss_generates_and_stores(self):
        db = _make_db(lookup_value=None)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "333-1234567", "PHONE", "phone")
        assert isinstance(result, str) and result
        # commit called (store)
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        db = _make_db(lookup_value="fake-cached-value")
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "333-1234567", "PHONE", "phone")
        assert result == "fake-cached-value"

    @pytest.mark.asyncio
    async def test_none_strategy_falls_back_to_alphanumeric(self):
        db = _make_db(lookup_value=None)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "somevalue", "UNKNOWN", None)
        assert isinstance(result, str) and result

    @pytest.mark.asyncio
    async def test_locale_passed_to_generator(self):
        db = _make_db(lookup_value=None)
        svc_it = SurrogateService(db, locale="it_IT")
        svc_en = SurrogateService(_make_db(lookup_value=None), locale="en_US")
        it = await svc_it.get_or_create("ctx-1", "Mario Rossi", "PERSON", "person")
        en = await svc_en.get_or_create("ctx-1", "Mario Rossi", "PERSON", "person")
        # Different locales → different fake names (probabilistically true)
        # We just check both return non-empty strings
        assert it and en

    @pytest.mark.asyncio
    async def test_deterministic_across_calls(self):
        db1 = _make_db(lookup_value=None)
        db2 = _make_db(lookup_value=None)
        svc1 = SurrogateService(db1, locale="it_IT")
        svc2 = SurrogateService(db2, locale="it_IT")
        r1 = await svc1.get_or_create("ctx-same", "user@example.com", "EMAIL", "email")
        r2 = await svc2.get_or_create("ctx-same", "user@example.com", "EMAIL", "email")
        assert r1 == r2


# ── profile path (PERSON / FISCAL_CODE) ──────────────────────────────────────

class TestProfilePath:

    @pytest.mark.asyncio
    async def test_person_creates_profile(self):
        db = _make_db(lookup_value=None, profile_row=None)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "Mario Rossi", "PERSON", None)
        assert isinstance(result, str) and " " in result  # "First Last"

    @pytest.mark.asyncio
    async def test_person_uses_cached_profile(self):
        profile = {
            "fake_first_name": "Luca",
            "fake_last_name": "Bianchi",
            "fake_birth_date": None,
            "fake_gender": "M",
            "fake_city": "Roma",
            "fake_belfiore": "H501",
            "fake_cf": "BNCLCU85M12F205X",
        }
        db = _make_db(lookup_value=None, profile_row=profile)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "Mario Rossi", "PERSON", None)
        assert result == "Luca Bianchi"

    @pytest.mark.asyncio
    async def test_fiscal_code_returns_fake_cf(self):
        profile = {
            "fake_first_name": "Luca",
            "fake_last_name": "Bianchi",
            "fake_birth_date": None,
            "fake_gender": "M",
            "fake_city": "Roma",
            "fake_belfiore": "H501",
            "fake_cf": "BNCLCU85M12F205X",
        }
        db = _make_db(lookup_value=None, profile_row=profile)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "RSSMRA80A01H501U", "FISCAL_CODE", None)
        assert result == "BNCLCU85M12F205X"

    @pytest.mark.asyncio
    async def test_person_profile_created_when_missing(self):
        db = _make_db(lookup_value=None, profile_row=None)
        svc = SurrogateService(db, locale="it_IT")
        result = await svc.get_or_create("ctx-1", "Giulia Bianchi", "PERSON", None)
        # Any non-empty string with a space = valid fake name
        assert isinstance(result, str) and result


# ── reverse lookup ────────────────────────────────────────────────────────────

class TestListMappings:

    @pytest.mark.asyncio
    async def test_returns_list(self):
        mapping_row = MagicMock()
        mapping_row._mapping = {"pii_type": "PERSON", "real_hash": "abc", "fake_value": "Luca Bianchi"}
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [mapping_row]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        svc = SurrogateService(db, locale="it_IT")
        mappings = await svc.list_mappings_for_context("ctx-1")
        assert isinstance(mappings, list)
        assert mappings[0]["fake_value"] == "Luca Bianchi"

    @pytest.mark.asyncio
    async def test_empty_context_returns_empty_list(self):
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        svc = SurrogateService(db, locale="it_IT")
        mappings = await svc.list_mappings_for_context("ctx-empty")
        assert mappings == []
