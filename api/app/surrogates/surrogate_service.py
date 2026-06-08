"""SurrogateService — DB-backed deterministic fake value generation."""

import hashlib
import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.surrogates import generators
from app.surrogates.cf_codec import decode_partial


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _normalise_name(name: str) -> str:
    return " ".join(name.lower().split())


class SurrogateService:
    def __init__(self, db: AsyncSession, locale: str = "it_IT") -> None:
        self._db = db
        self._locale = locale

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_or_create(
        self,
        context_id: str,
        real_value: str,
        pii_type: str,
        faker_strategy: str | None,
    ) -> str:
        """Return the fake value for real_value, creating and caching it if needed."""
        if pii_type in ("PERSON", "FISCAL_CODE"):
            return await self._profile_value(context_id, real_value, pii_type)
        return await self._simple_value(context_id, real_value, pii_type, faker_strategy)

    # ── Simple (non-profile) path ─────────────────────────────────────────────

    async def _simple_value(
        self, context_id: str, real_value: str, pii_type: str, strategy: str | None
    ) -> str:
        rh = _hash(real_value)
        cached = await self._lookup(context_id, pii_type, rh)
        if cached:
            return cached

        fake = generators.generate(strategy or "alphanumeric", real_value, context_id, self._locale)
        await self._store(context_id, pii_type, rh, fake)
        return fake

    # ── Profile path (PERSON / FISCAL_CODE) ──────────────────────────────────

    async def _profile_value(self, context_id: str, real_value: str, pii_type: str) -> str:
        if pii_type == "PERSON":
            key = _normalise_name(real_value)
            gender_hint = "M"
        else:
            key = real_value.upper().strip()
            decoded = decode_partial(key)
            gender_hint = decoded.get("gender", "M")

        profile = await self._get_or_create_profile(context_id, key, gender_hint)

        if pii_type == "PERSON":
            fake = f"{profile['fake_first_name']} {profile['fake_last_name']}"
        else:
            fake = profile["fake_cf"]

        # Also cache in surrogate_mappings for fast reverse lookup
        rh = _hash(real_value)
        await self._store(context_id, pii_type, rh, fake)
        return fake

    async def _get_or_create_profile(
        self, context_id: str, key: str, gender_hint: str
    ) -> dict:
        rh = _hash(key)
        result = await self._db.execute(
            text(
                "SELECT fake_first_name, fake_last_name, fake_birth_date, fake_gender,"
                "       fake_city, fake_belfiore, fake_cf"
                " FROM surrogate_profiles"
                " WHERE context_id = :ctx AND real_hash = :rh"
            ),
            {"ctx": context_id, "rh": rh},
        )
        row = result.fetchone()
        if row:
            return dict(row._mapping)

        profile = generators.gen_fake_profile(key, context_id, gender_hint, self._locale)
        await self._db.execute(
            text(
                "INSERT INTO surrogate_profiles"
                " (context_id, real_hash, fake_first_name, fake_last_name,"
                "  fake_birth_date, fake_gender, fake_city, fake_belfiore, fake_cf)"
                " VALUES (:ctx, :rh, :first, :last, :birth, :gender, :city, :belfiore, :cf)"
                " ON CONFLICT (context_id, real_hash) DO NOTHING"
            ),
            {
                "ctx": context_id, "rh": rh,
                "first": profile["fake_first_name"], "last": profile["fake_last_name"],
                "birth": profile["fake_birth_date"], "gender": profile["fake_gender"],
                "city": profile["fake_city"], "belfiore": profile["fake_belfiore"],
                "cf": profile["fake_cf"],
            },
        )
        await self._db.commit()
        return profile

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _lookup(self, context_id: str, pii_type: str, real_hash: str) -> str | None:
        result = await self._db.execute(
            text(
                "SELECT fake_value FROM surrogate_mappings"
                " WHERE context_id = :ctx AND pii_type = :t AND real_hash = :rh"
            ),
            {"ctx": context_id, "t": pii_type, "rh": real_hash},
        )
        row = result.fetchone()
        return row[0] if row else None

    async def _store(
        self, context_id: str, pii_type: str, real_hash: str, fake_value: str
    ) -> None:
        await self._db.execute(
            text(
                "INSERT INTO surrogate_mappings (context_id, pii_type, real_hash, fake_value)"
                " VALUES (:ctx, :t, :rh, :fv)"
                " ON CONFLICT (context_id, pii_type, real_hash) DO NOTHING"
            ),
            {"ctx": context_id, "t": pii_type, "rh": real_hash, "fv": fake_value},
        )
        await self._db.commit()

    # ── Reverse lookup (for de-anonymize) ────────────────────────────────────

    async def list_mappings_for_context(self, context_id: str) -> list[dict]:
        """Return all (fake_value, real_hash) for a context — used by de-anonymize."""
        result = await self._db.execute(
            text(
                "SELECT pii_type, real_hash, fake_value FROM surrogate_mappings"
                " WHERE context_id = :ctx ORDER BY length(fake_value) DESC"
            ),
            {"ctx": context_id},
        )
        return [dict(r._mapping) for r in result.fetchall()]
