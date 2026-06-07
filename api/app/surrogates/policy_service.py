"""Resolve which PII types to protect/keep for a given context_type + inline policy."""

import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        context_type: str | None,
        inline_policy: dict | None = None,
        inline_mode: str | None = None,
    ) -> tuple[set[str] | None, set[str], str]:
        """
        Returns (protect_types, keep_types, mode).
        protect_types = None means "protect everything not in keep_types".
        """
        # 1. Load context_type config from DB
        ct_domain = None
        ct_mode = "tag"
        if context_type:
            result = await self._db.execute(
                text("SELECT domain, default_mode FROM context_types WHERE code = :c AND enabled = true"),
                {"c": context_type},
            )
            row = result.fetchone()
            if row:
                ct_domain, ct_mode = row[0], row[1]

        # 2. Load domain policy
        protect: set[str] | None = None
        keep: set[str] = set()
        if ct_domain:
            result = await self._db.execute(
                text("SELECT protect_types, keep_types FROM domain_policies WHERE domain = :d AND enabled = true"),
                {"d": ct_domain},
            )
            row = result.fetchone()
            if row:
                protect_list = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
                keep_list    = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
                protect = set(protect_list)
                keep    = set(keep_list)

        # 3. Inline policy overrides domain policy
        if inline_policy:
            if "protect" in inline_policy:
                protect = set(inline_policy["protect"])
            if "keep" in inline_policy:
                keep = set(inline_policy.get("keep", []))

        # 4. Mode: inline > context_type default > "tag"
        mode = inline_mode or ct_mode or "tag"

        return protect, keep, mode

    async def get_faker_strategy(self, pii_type: str) -> str | None:
        result = await self._db.execute(
            text("SELECT faker_strategy FROM pii_type_registry WHERE code = :c"),
            {"c": pii_type},
        )
        row = result.fetchone()
        return row[0] if row else None
