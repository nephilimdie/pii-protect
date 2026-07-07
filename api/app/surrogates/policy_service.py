"""Resolve which PII types to protect/keep for a given context_type + inline policy."""

from __future__ import annotations
import hashlib
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.scoped_config.service import ScopedConfigService


class PolicyService:
    def __init__(self, db: AsyncSession, tenant_id: str | None = None) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._scoped_config = ScopedConfigService(db)

    async def resolve(
        self,
        context_type: str | None,
        inline_policy: dict | None = None,
        inline_mode: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """
        Returns (protect_types, keep_types, surrogate_types, mode).
        protect_types = None means "protect everything not in keep/surrogate".
        surrogate_types = types that are always replaced with a fake value,
                          regardless of the context-level mode.

        A direct `domain` invokes a domain policy as a self-contained unit,
        bypassing the context_type indirection. When both are given, `domain`
        wins. With `domain` the mode comes from the policy's own default_mode
        (unless overridden by inline_mode).

        When tenant_id is set (cloud mode), policy and context lookups are
        scoped to that tenant. When None (self-hosted), behaviour is unchanged.
        """
        # 1. Resolve which domain policy to load.
        #    Direct `domain` short-circuits the context_type lookup; ct_mode stays
        #    None so the policy's own default_mode applies downstream.
        ct_domain = None
        ct_mode = None
        ct_version = 1
        if domain:
            ct_domain = domain
        elif context_type:
            if self._tenant_id is not None:
                context_rows = await self._scoped_config.effective_items("context-types", "tenant", self._tenant_id)
                row_data = next((row for row in context_rows if row.get("code") == context_type and row.get("enabled", True)), None)
                row = (row_data.get("domain"), row_data.get("default_mode"), row_data.get("version", 1)) if row_data else None
            else:
                result = await self._db.execute(
                    text("SELECT domain, default_mode, version FROM context_types WHERE code = :c AND enabled = true AND tenant_id IS NULL"),
                    {"c": context_type},
                )
                row = result.fetchone()
            if row:
                ct_domain, ct_mode, ct_version = row[0], row[1], row[2]

        # 2. Load domain policy
        protect: set[str] | None = None
        keep: set[str] = set()
        surrogate: set[str] = set()
        remove: set[str] = set()
        block: set[str] = set()
        domain_version = 1
        policy_default_mode = None
        if ct_domain:
            if self._tenant_id is not None:
                policy_rows = await self._scoped_config.effective_items("domain-policies", "tenant", self._tenant_id)
                row_data = next((row for row in policy_rows if row.get("domain") == ct_domain and row.get("enabled", True)), None)
                row = (
                    row_data.get("protect_types", []),
                    row_data.get("keep_types", []),
                    row_data.get("surrogate_types", []),
                    row_data.get("remove_types", []),
                    row_data.get("block_types", []),
                    row_data.get("version", 1),
                    row_data.get("default_mode"),
                ) if row_data else None
            else:
                result = await self._db.execute(
                    text(
                        "SELECT protect_types, keep_types, surrogate_types, remove_types, block_types, version, default_mode"
                        " FROM domain_policies WHERE domain = :d AND enabled = true AND tenant_id IS NULL"
                    ),
                    {"d": ct_domain},
                )
                row = result.fetchone()
            if row:
                protect_list   = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
                keep_list      = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
                surrogate_list = row[2] if isinstance(row[2], list) else json.loads(row[2] or "[]")
                remove_list    = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
                block_list     = row[4] if isinstance(row[4], list) else json.loads(row[4] or "[]")
                domain_version = row[5] or 1
                policy_default_mode = row[6] if len(row) > 6 else None
                protect   = set(protect_list)
                keep      = set(keep_list)
                surrogate = set(surrogate_list)
                remove    = set(remove_list)
                block     = set(block_list)

        # 3. Inline policy overrides domain policy
        if inline_policy:
            if "protect" in inline_policy:
                protect   = set(inline_policy["protect"])
            if "keep" in inline_policy:
                keep      = set(inline_policy.get("keep", []))
            if "surrogate" in inline_policy:
                surrogate = set(inline_policy.get("surrogate", []))
            if "remove" in inline_policy:
                remove    = set(inline_policy.get("remove", []))
            if "block" in inline_policy:
                block     = set(inline_policy.get("block", []))

        # 4. Mode precedence: inline > context_type default > policy default_mode > "tag"
        #    (ct_mode is None when the caller invoked a domain directly, so the
        #     policy's own default_mode drives the render style.)
        mode = inline_mode or ct_mode or policy_default_mode or "tag"

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
                "remove": sorted(remove),
                "block": sorted(block),
            },
            sort_keys=True,
        )
        policy_hash = hashlib.sha256(policy_hash_payload.encode()).hexdigest()

        return {
            "protect_types": protect,
            "keep_types": keep,
            "surrogate_types": surrogate,
            "remove_types": remove,
            "block_types": block,
            "mode": mode,
            "policy_id": context_type or (f"domain:{ct_domain}" if ct_domain else None),
            "policy_version": f"context:{ct_version}|domain:{domain_version}",
            "policy_hash": policy_hash,
        }

    async def get_faker_strategy(self, pii_type: str) -> str | None:
        if self._tenant_id is not None:
            pii_rows = await self._scoped_config.effective_items("pii-types", "tenant", self._tenant_id)
            row = next((row for row in pii_rows if row.get("code") == pii_type and row.get("enabled", True)), None)
            if row:
                return row.get("faker_strategy")

        result = await self._db.execute(
            text("SELECT faker_strategy FROM pii_type_registry WHERE code = :c"),
            {"c": pii_type},
        )
        row = result.fetchone()
        return row[0] if row else None
