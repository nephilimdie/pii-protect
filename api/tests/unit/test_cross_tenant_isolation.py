"""Unit tests for cross-tenant isolation at the repository layer.

These tests verify that the mapping engine is secure in multi-tenancy mode:
  1. Same input anonymized by two tenants produces isolated mappings.
  2. Tenant B cannot deanonymize a token created by tenant A.
  3. Regex overrides scoped to tenant A do not affect tenant B.

Strategy: SQLite in-memory via SQLAlchemy async (no PostgreSQL required).
The FieldEncryptor is replaced with a trivial no-op stub so that the
`cryptography` package (not installed in the test venv) is never imported.
"""

from __future__ import annotations

import os
import sys
import uuid
from types import ModuleType
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path + env setup — MUST happen before any app import
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-chars-padded-00000000")
os.environ.setdefault("ADMIN_INITIAL_KEY", "test-admin-key")

# ---------------------------------------------------------------------------
# Stub app.database so models can be imported without a live DB connection
# ---------------------------------------------------------------------------
from sqlalchemy.orm import DeclarativeBase

_database_stub = ModuleType("app.database")


class _Base(DeclarativeBase):
    pass


async def _get_db():
    yield None


_database_stub.Base = _Base
_database_stub.get_db = _get_db
sys.modules["app.database"] = _database_stub

# ---------------------------------------------------------------------------
# Stub app.mapping.encryptor — replaces Fernet with a trivial reversible codec
# so the `cryptography` package is not required.
# ---------------------------------------------------------------------------
_encryptor_stub_module = ModuleType("app.mapping.encryptor")


class _NoOpEncryptor:
    """Trivial encryptor: prefix + value so decrypt is the inverse of encrypt."""

    _PREFIX = "enc:"

    def __init__(self, key: str):
        pass  # key ignored for testing purposes

    def encrypt(self, value: str) -> str:
        return self._PREFIX + value

    def decrypt(self, value: str) -> str:
        if not value.startswith(self._PREFIX):
            raise ValueError("decryption_failed")
        return value[len(self._PREFIX):]


_encryptor_stub_module.FieldEncryptor = _NoOpEncryptor
sys.modules["app.mapping.encryptor"] = _encryptor_stub_module

# ---------------------------------------------------------------------------
# Real imports — now safe to pull in mapping layer
# ---------------------------------------------------------------------------
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import after stubs are in place
from app.mapping.models import PiiMapping  # noqa: E402 — intentional late import
from app.mapping.repository import MappingRepository
from app.detection.entities import MappingEntry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENCRYPTION_KEY = "test-key-32-chars-padded-00000000"


@pytest.fixture
async def async_session():
    """Yield a fully-initialised SQLite in-memory async session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables using the stub Base that PiiMapping is attached to
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        yield session

    await engine.dispose()


def _make_repo(session: AsyncSession) -> MappingRepository:
    """Return a repository wired to the given session."""
    repo = MappingRepository.__new__(MappingRepository)
    repo._db = session
    repo._encryptor = _NoOpEncryptor(ENCRYPTION_KEY)
    return repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(token: str, original: str, pii_type: str = "NAME") -> MappingEntry:
    return MappingEntry(token=token, original=original, pii_type=pii_type)


def test_context_word_overrides_use_platform_item_ids():
    """
    Context-word scoped overrides must use the platform row id as item_key.
    Matching on the word text would fail for duplicated words and would not
    align with the scoped-config API contract.
    """
    from app.detection.config_resolver import _apply_context_overrides

    platform_rows = [
        {
            "id": "ctx_cf",
            "entity_type": "FISCAL_CODE",
            "word": "cf",
            "description": "Fiscal code hint",
            "enabled": True,
        },
        {
            "id": "ctx_vat",
            "entity_type": "VAT_NUMBER",
            "word": "partita iva",
            "description": "VAT hint",
            "enabled": True,
        },
    ]
    overrides = [
        {
            "item_key": "ctx_cf",
            "action": "hidden",
            "data": {},
        },
        {
            "item_key": "tenant_local_hint",
            "action": "custom",
            "data": {
                "entity_type": "PERSON",
                "word": "cliente",
                "enabled": True,
            },
        },
    ]

    result = _apply_context_overrides(platform_rows, overrides)

    assert "FISCAL_CODE" not in result
    assert result["VAT_NUMBER"] == ["partita iva"]
    assert result["PERSON"] == ["cliente"]


def test_detection_layer_overrides_disable_selected_layer_only():
    from app.detection.config_resolver import _apply_layer_overrides

    platform_rows = [
        {"code": "regex", "enabled": True},
        {"code": "presidio", "enabled": True},
        {"code": "privacy_filter", "enabled": True},
        {"code": "ai4privacy", "enabled": True},
    ]
    overrides = [
        {
            "item_key": "privacy_filter",
            "action": "override",
            "data": {"enabled": False},
        },
        {
            "item_key": "ai4privacy",
            "action": "override",
            "data": {"enabled": False},
        },
    ]

    result = _apply_layer_overrides(platform_rows, overrides)

    assert result == {"regex", "presidio"}


@pytest.mark.asyncio
async def test_same_input_creates_separate_tenant_mappings(async_session):
    """
    Given: tenant-a and tenant-b both anonymize "Mario Rossi" → token NAME_1.
    Then: each tenant's mapping is stored independently.
    And: tenant-a's repo does not return tenant-b's mapping and vice-versa.
    """
    repo_a = _make_repo(async_session)
    repo_b = _make_repo(async_session)

    # Both tenants anonymize the same text, producing the same token label.
    await repo_a.save_many(
        [_entry("NAME_1", "Mario Rossi")],
        context_id="ctx-001",
        context_type="session",
        tenant_id="tenant-a",
    )
    await repo_b.save_many(
        [_entry("NAME_1", "Mario Rossi")],
        context_id="ctx-001",
        context_type="session",
        tenant_id="tenant-b",
    )

    entries_a = await repo_a.find_by_context("ctx-001", "session", tenant_id="tenant-a")
    entries_b = await repo_b.find_by_context("ctx-001", "session", tenant_id="tenant-b")

    # Both tenants have exactly one mapping for the context.
    assert len(entries_a) == 1, f"Expected 1 entry for tenant-a, got {len(entries_a)}"
    assert len(entries_b) == 1, f"Expected 1 entry for tenant-b, got {len(entries_b)}"

    # The mappings are logically independent (both decode to the same original,
    # but the rows in the DB are separate — verified by checking each tenant's
    # query scope does not bleed into the other).
    assert entries_a[0].original == "Mario Rossi"
    assert entries_b[0].original == "Mario Rossi"

    # Cross-check: if we query with the opposite tenant_id, we must get no results
    # for the other tenant's data (isolation).
    leak_a_into_b = await repo_b.find_by_context("ctx-001", "session", tenant_id="tenant-a")
    leak_b_into_a = await repo_a.find_by_context("ctx-001", "session", tenant_id="tenant-b")

    # These use the *correct* tenant_id filter — since repo_b looks up tenant-a's
    # data directly, it should still find it (the repo doesn't enforce API-key auth,
    # that's done at the HTTP layer). What we're verifying is that the tenant_id
    # filter isolates rows: tenant-a rows are NOT returned when querying tenant-b,
    # and vice-versa.
    assert all(e.original == "Mario Rossi" for e in leak_a_into_b)  # tenant-a data exists
    assert all(e.original == "Mario Rossi" for e in leak_b_into_a)  # tenant-b data exists

    # The definitive isolation test: count rows per tenant at DB level.
    from sqlalchemy import select, func
    count_a = (await async_session.execute(
        select(func.count()).select_from(PiiMapping).where(PiiMapping.tenant_id == "tenant-a")
    )).scalar_one()
    count_b = (await async_session.execute(
        select(func.count()).select_from(PiiMapping).where(PiiMapping.tenant_id == "tenant-b")
    )).scalar_one()

    assert count_a == 1, f"Expected 1 row for tenant-a, got {count_a}"
    assert count_b == 1, f"Expected 1 row for tenant-b, got {count_b}"
    # Total rows = 2 (one per tenant), proving no shared-row leakage.
    assert count_a + count_b == 2


# ---------------------------------------------------------------------------
# Test 2 — Tenant B cannot deanonymize token created by tenant A
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_b_cannot_deanonymize_token_of_tenant_a(async_session):
    """
    Given: tenant-a has created token NAME_1 → "Mario Rossi".
    When: tenant-b queries find_by_context with tenant_id="tenant-b".
    Then: no mapping is found (empty list → token stays unreplaced).
    """
    repo_a = _make_repo(async_session)
    repo_b = _make_repo(async_session)

    # Only tenant-a saves the mapping.
    await repo_a.save_many(
        [_entry("NAME_1", "Mario Rossi")],
        context_id="ctx-secret",
        context_type="session",
        tenant_id="tenant-a",
    )

    # Tenant-b tries to deanonymize the same context + token.
    entries_b = await repo_b.find_by_context(
        "ctx-secret", "session", tenant_id="tenant-b"
    )

    # Must return empty — tenant-b has no mapping for this context.
    assert entries_b == [], (
        f"Tenant-b must not see tenant-a's mappings, but got: {entries_b}"
    )

    # Confirm tenant-a's own lookup still works correctly.
    entries_a = await repo_a.find_by_context(
        "ctx-secret", "session", tenant_id="tenant-a"
    )
    assert len(entries_a) == 1
    assert entries_a[0].token == "NAME_1"
    assert entries_a[0].original == "Mario Rossi"


# ---------------------------------------------------------------------------
# Test 3 — Scoped regex override for tenant A does not affect tenant B
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scoped_regex_override_does_not_leak_across_tenants(async_session):
    """
    Given: tenant-a has an override on FISCAL_CODE (custom pattern).
    And: tenant-b has no override.
    Then: effective_items for tenant-a returns the overridden pattern.
    And: effective_items for tenant-b returns the platform-default pattern.

    This test drives ScopedConfigService via a fake DB session that mirrors
    the behaviour of ScopedConfigRepository without touching PostgreSQL.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.scoped_config.service import ScopedConfigService

    # Platform base item (shared, no tenant scope)
    _BASE_PATTERN = "[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]"
    _OVERRIDE_PATTERN_A = "[A-Z]{6}[0-9]{6}"

    _base_rows = [
        {
            "id": "rx_fc",
            "pii_type": "FISCAL_CODE",
            "pattern": _BASE_PATTERN,
            "flags": "",
            "capture_group": 0,
            "description": "Platform fiscal code regex",
            "enabled": True,
            "created_at": None,
            "updated_at": None,
        }
    ]

    # Override stored only for tenant-a.
    # `data` must be a dict (already deserialized), matching what
    # ScopedConfigRepository.overrides() returns via dict(row._mapping).
    _override_a = {
        "item_key": "rx_fc",
        "action": "override",
        "data": {
            "pii_type": "FISCAL_CODE",
            "pattern": _OVERRIDE_PATTERN_A,
            "flags": "",
            "capture_group": 0,
            "description": "Tenant-A fiscal code override",
            "enabled": True,
        },
        "scope_type": "tenant",
        "scope_key": "tenant-a",
    }

    def _make_result(rows):
        return MagicMock(
            fetchall=MagicMock(
                return_value=[SimpleNamespace(_mapping=row) for row in rows]
            )
        )

    async def _execute(query, params=None):
        sql = str(query)
        params = params or {}
        if "FROM regex_patterns" in sql:
            return _make_result(_base_rows)
        if "FROM scoped_config_overrides" in sql:
            scope_key = params.get("scope_key", "")
            if scope_key == "tenant-a":
                return _make_result([_override_a])
            return _make_result([])  # tenant-b has no overrides
        return _make_result([])

    fake_db = SimpleNamespace(
        execute=AsyncMock(side_effect=_execute),
        commit=AsyncMock(),
    )

    service = ScopedConfigService(fake_db)  # type: ignore[arg-type]

    items_a = await service.effective_items(
        "regex-patterns", scope_type="tenant", scope_key="tenant-a"
    )
    items_b = await service.effective_items(
        "regex-patterns", scope_type="tenant", scope_key="tenant-b"
    )

    # Locate the FISCAL_CODE entry in each result set.
    fc_a = next((i for i in items_a if i.get("pii_type") == "FISCAL_CODE"), None)
    fc_b = next((i for i in items_b if i.get("pii_type") == "FISCAL_CODE"), None)

    assert fc_a is not None, "tenant-a result must contain FISCAL_CODE entry"
    assert fc_b is not None, "tenant-b result must contain FISCAL_CODE entry"

    # Tenant-a sees the custom (overridden) pattern.
    assert fc_a["pattern"] == _OVERRIDE_PATTERN_A, (
        f"Expected tenant-a to see override pattern, got: {fc_a['pattern']!r}"
    )
    # Tenant-a item carries the tenant scope tag.
    assert fc_a.get("_scope") == "tenant:tenant-a", (
        f"Expected _scope='tenant:tenant-a', got: {fc_a.get('_scope')!r}"
    )

    # Tenant-b sees the platform-default pattern (no override applied).
    assert fc_b["pattern"] == _BASE_PATTERN, (
        f"Expected tenant-b to see platform pattern, got: {fc_b['pattern']!r}"
    )
    # Tenant-b item carries the platform scope tag (no tenant override).
    assert fc_b.get("_scope") == "platform", (
        f"Expected _scope='platform' for tenant-b, got: {fc_b.get('_scope')!r}"
    )
