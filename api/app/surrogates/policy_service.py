"""Resolve which PII types to protect/keep for a given context_type + inline policy."""

import hashlib
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
    ) -> dict:
        """
        Returns (protect_types, keep_types, surrogate_types, mode).
        protect_types = None means "protect everything not in keep/surrogate".
        surrogate_types = types that are always replaced with a fake value,
                          regardless of the context-level mode.
        """
        # 1. Load context_type config from DB
        ct_domain = None
        ct_mode = "tag"
        ct_version = 1
        if context_type:
            result = await self._db.execute(
                text("SELECT domain, default_mode, version FROM context_types WHERE code = :c AND enabled = true"),
                {"c": context_type},
            )
            row = result.fetchone()
            if row:
                ct_domain, ct_mode, ct_version = row[0], row[1], row[2]

        # 2. Load domain policy
        protect: set[str] | None = None
        keep: set[str] = set()
        surrogate: set[str] = set()
        domain_version = 1
        if ct_domain:
            result = await self._db.execute(
                text("SELECT protect_types, keep_types, surrogate_types, version FROM domain_policies WHERE domain = :d AND enabled = true"),
                {"d": ct_domain},
            )
            row = result.fetchone()
            if row:
                protect_list   = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
                keep_list      = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
                surrogate_list = row[2] if isinstance(row[2], list) else json.loads(row[2] or "[]")
                domain_version = row[3] or 1
                protect   = set(protect_list)
                keep      = set(keep_list)
                surrogate = set(surrogate_list)

        # 3. Inline policy overrides domain policy
        if inline_policy:
            if "protect" in inline_policy:
                protect   = set(inline_policy["protect"])
            if "keep" in inline_policy:
                keep      = set(inline_policy.get("keep", []))
            if "surrogate" in inline_policy:
                surrogate = set(inline_policy.get("surrogate", []))

        # 4. Mode: inline > context_type default > "tag"
        mode = inline_mode or ct_mode or "tag"

        policy_hash_payload = json.dumps(
            {
                "context_type": context_type,
                "context_version": ct_version,
                "domain": ct_domain,
                "domain_version": domain_version,
                "mode": mode,
                "protect": sorted(protect) if protect is not None else None,
                "keep": sorted(keep),
                "surrogate": sorted(surrogate),
            },
            sort_keys=True,
        )
        policy_hash = hashlib.sha256(policy_hash_payload.encode()).hexdigest()

        return {
            "protect_types": protect,
            "keep_types": keep,
            "surrogate_types": surrogate,
            "mode": mode,
            "policy_id": context_type,
            "policy_version": f"context:{ct_version}|domain:{domain_version}",
            "policy_hash": policy_hash,
        }

    async def get_faker_strategy(self, pii_type: str) -> str | None:
        result = await self._db.execute(
            text("SELECT faker_strategy FROM pii_type_registry WHERE code = :c"),
            {"c": pii_type},
        )
        row = result.fetchone()
        return row[0] if row else None
