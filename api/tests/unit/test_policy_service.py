"""Unit tests for PolicyService — DB mocked with AsyncMock."""

import sys
import os
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, MagicMock
from app.surrogates.policy_service import PolicyService


def _make_db(fetchone_return=None):
    """Build a minimal AsyncSession mock."""
    result_mock = MagicMock()
    result_mock.fetchone.return_value = fetchone_return

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ── resolve() ────────────────────────────────────────────────────────────────

class TestPolicyServiceResolve:

    @pytest.mark.asyncio
    async def test_no_context_type_returns_tag_mode(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        resolved = await svc.resolve(context_type=None)
        assert resolved["mode"] == "tag"
        assert resolved["protect_types"] is None
        assert resolved["keep_types"] == set()
        assert resolved["surrogate_types"] == set()
        assert resolved["policy_version"] == "context:1|domain:1"

    @pytest.mark.asyncio
    async def test_unknown_context_type_returns_defaults(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        resolved = await svc.resolve(context_type="nonexistent")
        assert resolved["mode"] == "tag"
        assert resolved["protect_types"] is None

    @pytest.mark.asyncio
    async def test_context_type_with_domain_policy(self):
        # First call returns context_type row; second returns domain policy row
        ct_row = ("fine_appeal", "tag", 2)
        policy_row = (["PERSON", "FISCAL_CODE"], ["DATE", "TARGA"], [], [], [], 3)

        results = [MagicMock(fetchone=MagicMock(return_value=ct_row)),
                   MagicMock(fetchone=MagicMock(return_value=policy_row))]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=results)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type="fine_appeal")

        assert "PERSON" in resolved["protect_types"]
        assert "FISCAL_CODE" in resolved["protect_types"]
        assert "DATE" in resolved["keep_types"]
        assert "TARGA" in resolved["keep_types"]
        assert resolved["mode"] == "tag"
        assert resolved["policy_version"] == "context:2|domain:3"

    @pytest.mark.asyncio
    async def test_inline_policy_overrides_domain(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        inline = {"protect": ["EMAIL"], "keep": ["DATE"], "surrogate": ["PHONE"]}
        resolved = await svc.resolve(
            context_type=None, inline_policy=inline
        )
        assert resolved["protect_types"] == {"EMAIL"}
        assert resolved["keep_types"] == {"DATE"}
        assert resolved["surrogate_types"] == {"PHONE"}

    @pytest.mark.asyncio
    async def test_inline_mode_overrides_context_type(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        resolved = await svc.resolve(
            context_type=None, inline_mode="surrogate"
        )
        assert resolved["mode"] == "surrogate"

    @pytest.mark.asyncio
    async def test_inline_policy_partial_override(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        # Only protect key in inline — keep and surrogate stay empty
        inline = {"protect": ["PERSON"]}
        resolved = await svc.resolve(
            context_type=None, inline_policy=inline
        )
        assert resolved["protect_types"] == {"PERSON"}
        assert resolved["keep_types"] == set()
        assert resolved["surrogate_types"] == set()

    @pytest.mark.asyncio
    async def test_domain_policy_with_json_string_columns(self):
        # Some DB drivers return JSONB as raw JSON strings
        ct_row = ("default", "surrogate", 4)
        policy_row = ('["PERSON"]', '["DATE"]', '["EMAIL"]', '[]', '[]', 5)

        results = [MagicMock(fetchone=MagicMock(return_value=ct_row)),
                   MagicMock(fetchone=MagicMock(return_value=policy_row))]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=results)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type="default")

        assert "PERSON" in resolved["protect_types"]
        assert "DATE" in resolved["keep_types"]
        assert "EMAIL" in resolved["surrogate_types"]
        assert resolved["mode"] == "surrogate"
        assert resolved["policy_version"] == "context:4|domain:5"

    @pytest.mark.asyncio
    async def test_domain_direct_uses_policy_default_mode(self):
        # Calling by `domain` skips the context_type lookup entirely: only the
        # domain policy row is fetched, and mode comes from its default_mode.
        policy_row = (["PERSON"], ["DATE"], [], [], [], 7, "surrogate")
        db = _make_db(fetchone_return=policy_row)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type=None, domain="condominio")

        assert "PERSON" in resolved["protect_types"]
        assert "DATE" in resolved["keep_types"]
        assert resolved["mode"] == "surrogate"
        assert resolved["policy_id"] == "domain:condominio"
        # Exactly one DB round-trip (no context_type lookup)
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_domain_direct_defaults_to_tag_when_policy_mode_missing(self):
        # Legacy 6-tuple (no default_mode column) falls back to "tag".
        policy_row = (["PERSON"], ["DATE"], [], [], [], 2)
        db = _make_db(fetchone_return=policy_row)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type=None, domain="condominio")

        assert resolved["mode"] == "tag"

    @pytest.mark.asyncio
    async def test_domain_wins_over_context_type(self):
        # When both are given, `domain` is used and context_type is ignored.
        policy_row = (["EMAIL"], [], [], [], [], 1, "tag")
        db = _make_db(fetchone_return=policy_row)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type="fine_appeal", domain="medical")

        assert "EMAIL" in resolved["protect_types"]
        assert resolved["policy_id"] == "fine_appeal"  # metadata keeps caller's context_type
        assert db.execute.await_count == 1  # context_type lookup skipped

    @pytest.mark.asyncio
    async def test_inline_mode_overrides_domain_default(self):
        policy_row = (["PERSON"], [], [], [], [], 1, "surrogate")
        db = _make_db(fetchone_return=policy_row)

        svc = PolicyService(db)
        resolved = await svc.resolve(context_type=None, domain="condominio", inline_mode="tag")

        assert resolved["mode"] == "tag"


# ── get_faker_strategy() ──────────────────────────────────────────────────────

class TestGetFakerStrategy:

    @pytest.mark.asyncio
    async def test_returns_strategy_string(self):
        row = MagicMock()
        row.__getitem__ = lambda self, i: "person"
        db = _make_db(fetchone_return=row)
        svc = PolicyService(db)
        result = await svc.get_faker_strategy("PERSON")
        assert result == "person"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_type(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        result = await svc.get_faker_strategy("UNKNOWN_TYPE")
        assert result is None
