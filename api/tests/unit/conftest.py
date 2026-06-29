"""
Shared fixtures and stubs for all unit tests.

This file is collected by pytest before any test module, so stubs registered
here are guaranteed to be in sys.modules before any app code is imported.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from sqlalchemy.orm import DeclarativeBase

# ── Environment defaults ──────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-chars-padded-00000000")
os.environ.setdefault("ADMIN_INITIAL_KEY", "test-admin-key")

# ── app.database stub ─────────────────────────────────────────────────────────
if "app.database" not in sys.modules:
    _database_stub = ModuleType("app.database")

    class _Base(DeclarativeBase):
        pass

    async def _get_db():
        yield None

    _database_stub.Base = _Base
    _database_stub.get_db = _get_db
    sys.modules["app.database"] = _database_stub

# ── app.mapping.encryptor stub ────────────────────────────────────────────────
# Replaces Fernet-backed FieldEncryptor with a trivial prefix codec so that
# unit tests do not depend on a valid Fernet key or the cryptography package.
if "app.mapping.encryptor" not in sys.modules:
    _encryptor_stub = ModuleType("app.mapping.encryptor")

    class _NoOpEncryptor:
        _PREFIX = "enc:"

        def __init__(self, key: str):
            pass

        def encrypt(self, value: str) -> str:
            return self._PREFIX + value

        def decrypt(self, value: str) -> str:
            if not value.startswith(self._PREFIX):
                raise ValueError("decryption_failed")
            return value[len(self._PREFIX):]

    _encryptor_stub.FieldEncryptor = _NoOpEncryptor
    sys.modules["app.mapping.encryptor"] = _encryptor_stub
