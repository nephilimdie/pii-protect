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
        protect, keep, surrogate, mode = await svc.resolve(context_type=None)
        assert mode == "tag"
        assert protect is None
        assert keep == set()
        assert surrogate == set()

    @pytest.mark.asyncio
    async def test_unknown_context_type_returns_defaults(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        protect, keep, surrogate, mode = await svc.resolve(context_type="nonexistent")
        assert mode == "tag"
        assert protect is None

    @pytest.mark.asyncio
    async def test_context_type_with_domain_policy(self):
        # First call returns context_type row; second returns domain policy row
        ct_row = MagicMock()
        ct_row.__getitem__ = lambda self, i: ("fine_appeal" if i == 0 else "tag")

        policy_row = MagicMock()
        policy_row.__getitem__ = lambda self, i: (
            ["PERSON", "FISCAL_CODE"] if i == 0
            else (["DATE", "TARGA"] if i == 1 else [])
        )

        results = [MagicMock(fetchone=MagicMock(return_value=ct_row)),
                   MagicMock(fetchone=MagicMock(return_value=policy_row))]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=results)

        svc = PolicyService(db)
        protect, keep, surrogate, mode = await svc.resolve(context_type="fine_appeal")

        assert "PERSON" in protect
        assert "FISCAL_CODE" in protect
        assert "DATE" in keep
        assert "TARGA" in keep
        assert mode == "tag"

    @pytest.mark.asyncio
    async def test_inline_policy_overrides_domain(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        inline = {"protect": ["EMAIL"], "keep": ["DATE"], "surrogate": ["PHONE"]}
        protect, keep, surrogate, mode = await svc.resolve(
            context_type=None, inline_policy=inline
        )
        assert protect == {"EMAIL"}
        assert keep == {"DATE"}
        assert surrogate == {"PHONE"}

    @pytest.mark.asyncio
    async def test_inline_mode_overrides_context_type(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        protect, keep, surrogate, mode = await svc.resolve(
            context_type=None, inline_mode="surrogate"
        )
        assert mode == "surrogate"

    @pytest.mark.asyncio
    async def test_inline_policy_partial_override(self):
        db = _make_db(fetchone_return=None)
        svc = PolicyService(db)
        # Only protect key in inline — keep and surrogate stay empty
        inline = {"protect": ["PERSON"]}
        protect, keep, surrogate, mode = await svc.resolve(
            context_type=None, inline_policy=inline
        )
        assert protect == {"PERSON"}
        assert keep == set()
        assert surrogate == set()

    @pytest.mark.asyncio
    async def test_domain_policy_with_json_string_columns(self):
        # Some DB drivers return JSONB as raw JSON strings
        ct_row = MagicMock()
        ct_row.__getitem__ = lambda self, i: ("default" if i == 0 else "surrogate")

        policy_row = MagicMock()
        policy_row.__getitem__ = lambda self, i: (
            '["PERSON"]' if i == 0
            else ('["DATE"]' if i == 1 else '["EMAIL"]')
        )

        results = [MagicMock(fetchone=MagicMock(return_value=ct_row)),
                   MagicMock(fetchone=MagicMock(return_value=policy_row))]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=results)

        svc = PolicyService(db)
        protect, keep, surrogate, mode = await svc.resolve(context_type="default")

        assert "PERSON" in protect
        assert "DATE" in keep
        assert "EMAIL" in surrogate
        assert mode == "surrogate"


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
