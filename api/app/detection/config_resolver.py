"""
Detection config resolvers.

- GlobalDetectionConfigResolver: self-hosted, uses only platform-global config (no DB scoped queries).
- CloudScopedDetectionConfigResolver: cloud/tenant-aware, merges global config with per-tenant
  scoped_config_overrides from the database.
- resolve_detection_config(): factory function — picks the right resolver based on tenant_id.
- DetectionConfigResolver: legacy compatibility alias kept so existing callers keep working.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

_CACHE_TTL_SECONDS = 60.0


@dataclass
class ResolvedDetectionConfig:
    denylist: dict[str, dict]
    reclassification_rules: list[dict]
    regex_patterns: list[dict]
    presidio_context: dict[str, list[str]]


# In-process cache: cache_key (tenant_id or "") -> (timestamp, ResolvedDetectionConfig)
_cache: dict[str, tuple[float, ResolvedDetectionConfig]] = {}


# ── Static helpers (shared between both resolvers) ───────────────────────────

def _apply_list_overrides(
    platform: list[dict],
    overrides: list[dict],
    id_field: str,
) -> list[dict]:
    hidden: set[str] = set()
    data_map: dict[str, dict] = {}
    for ov in overrides:
        key = ov["item_key"]
        if ov["action"] == "hidden":
            hidden.add(key)
        elif ov["action"] == "override" and ov.get("data"):
            data_map[key] = ov["data"] if isinstance(ov["data"], dict) else {}

    result = []
    for item in platform:
        key = str(item.get(id_field, ""))
        if key in hidden:
            continue
        if key in data_map:
            result.append({**item, **data_map[key]})
        else:
            result.append(item)
    return result


def _apply_denylist_overrides(
    platform_raw: list[dict],
    overrides: list[dict],
) -> dict[str, dict]:
    """Re-build the denylist dict from raw rows + overrides."""
    hidden: set[str] = set()
    data_map: dict[str, dict] = {}
    for ov in overrides:
        key = ov["item_key"]
        if ov["action"] == "hidden":
            hidden.add(key)
        elif ov["action"] == "override" and ov.get("data"):
            data_map[key] = ov["data"] if isinstance(ov["data"], dict) else {}

    denylist: dict[str, dict] = {}
    for entry in platform_raw:
        key = str(entry.get("id", ""))
        if key in hidden:
            continue
        row = {**entry, **data_map.get(key, {})}
        if not row.get("enabled", True):
            continue
        pii_type = row["pii_type"]
        bucket = denylist.setdefault(pii_type, {"exact": set(), "contains": []})
        if row.get("match_type") == "contains":
            bucket["contains"].append(row["value"].lower())
        else:
            bucket["exact"].add(row["value"].lower())
    return denylist


def _apply_context_overrides(
    platform_raw: list[dict],
    overrides: list[dict],
) -> dict[str, list[str]]:
    """Re-build Presidio context words from raw rows + scoped overrides."""
    hidden: set[str] = set()
    data_map: dict[str, dict] = {}
    custom_items: list[dict] = []

    for ov in overrides:
        key = str(ov["item_key"])
        if ov["action"] == "hidden":
            hidden.add(key)
            continue
        if ov["action"] not in {"override", "custom"} or not ov.get("data"):
            continue

        data = ov["data"] if isinstance(ov["data"], dict) else {}
        if ov["action"] == "custom":
            custom_items.append(data)
        else:
            data_map[key] = data

    result: dict[str, list[str]] = {}
    for entry in platform_raw:
        key = str(entry.get("id", ""))
        if key in hidden:
            continue
        row = {**entry, **data_map.get(key, {})}
        if not row.get("enabled", True):
            continue
        _append_context_word(result, row)

    for item in custom_items:
        if item.get("enabled", True):
            _append_context_word(result, item)

    return result


def _append_context_word(result: dict[str, list[str]], item: dict) -> None:
    entity_type = item.get("entity_type")
    word = item.get("word")
    if not entity_type or not word:
        return
    bucket = result.setdefault(entity_type, [])
    if word not in bucket:
        bucket.append(word)


# ── GlobalDetectionConfigResolver ────────────────────────────────────────────

class GlobalDetectionConfigResolver:
    """
    Self-hosted resolver. Uses only platform-global config; never queries
    scoped_config_overrides. tenant_id is always None.
    """

    @classmethod
    async def for_request(cls, app_state: Any) -> ResolvedDetectionConfig:
        """Return the platform-global detection config, using cache when fresh."""
        cache_key = ""
        cached = _cache.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        config = ResolvedDetectionConfig(
            denylist=getattr(app_state, "denylist", {}),
            reclassification_rules=getattr(app_state, "reclassification_rules_raw", []),
            regex_patterns=getattr(app_state, "regex_patterns_raw", []),
            presidio_context=getattr(app_state, "presidio_context", {}),
        )
        _cache[cache_key] = (time.monotonic(), config)
        return config

    @classmethod
    def invalidate(cls) -> None:
        """Force cache invalidation for platform-global config."""
        _cache.pop("", None)


# ── CloudScopedDetectionConfigResolver ───────────────────────────────────────

class CloudScopedDetectionConfigResolver:
    """
    Cloud resolver. Merges platform-global config with per-tenant
    scoped_config_overrides. Requires a valid tenant_id.
    """

    def __init__(self, db: AsyncSession, tenant_id: str) -> None:
        self._db = db
        self._tenant_id = tenant_id

    @classmethod
    async def for_request(
        cls, db: AsyncSession, tenant_id: str, app_state: Any
    ) -> ResolvedDetectionConfig:
        """Return effective detection config for the tenant, using cache when fresh."""
        resolver = cls(db, tenant_id)
        cache_key = tenant_id
        cached = _cache.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        config = await resolver._build(app_state)
        _cache[cache_key] = (time.monotonic(), config)
        return config

    @classmethod
    def invalidate(cls, tenant_id: str) -> None:
        """Force cache invalidation for a specific tenant."""
        _cache.pop(tenant_id, None)

    async def _build(self, app_state: Any) -> ResolvedDetectionConfig:
        overrides = await self._load_overrides()
        return ResolvedDetectionConfig(
            denylist=_apply_denylist_overrides(
                getattr(app_state, "denylist_raw", []),
                overrides.get("denylist", []),
            ),
            reclassification_rules=_apply_list_overrides(
                getattr(app_state, "reclassification_rules_raw", []),
                overrides.get("reclassification", []),
                id_field="id",
            ),
            regex_patterns=_apply_list_overrides(
                getattr(app_state, "regex_patterns_raw", []),
                overrides.get("regex-patterns", []),
                id_field="id",
            ),
            presidio_context=_apply_context_overrides(
                getattr(app_state, "presidio_context_raw", []),
                overrides.get("context-words", []),
            ),
        )

    async def _load_overrides(self) -> dict[str, list[dict]]:
        result = await self._db.execute(
            text(
                "SELECT collection, item_key, action, data"
                " FROM scoped_config_overrides"
                " WHERE scope_type = 'tenant' AND scope_key = :tenant_id"
                " AND collection IN ('regex-patterns', 'denylist', 'context-words', 'reclassification')"
            ),
            {"tenant_id": self._tenant_id},
        )
        out: dict[str, list[dict]] = {}
        for row in result.fetchall():
            d = dict(row._mapping)
            out.setdefault(d["collection"], []).append(d)
        return out


# ── Factory function ──────────────────────────────────────────────────────────

async def resolve_detection_config(
    db: AsyncSession, app_state: Any, tenant_id: str | None
) -> ResolvedDetectionConfig:
    """
    Factory: uses GlobalDetectionConfigResolver when tenant_id is None,
    CloudScopedDetectionConfigResolver otherwise.
    """
    if tenant_id is None:
        return await GlobalDetectionConfigResolver.for_request(app_state)
    return await CloudScopedDetectionConfigResolver.for_request(db, tenant_id, app_state)


# ── Legacy compatibility shim ─────────────────────────────────────────────────

class DetectionConfigResolver:
    """
    Backward-compatible wrapper. Existing callers that do:
        resolver = DetectionConfigResolver(db, tenant_id)
        cfg = await resolver.resolve(app_state)
    continue to work unchanged.
    """

    def __init__(self, db: AsyncSession, tenant_id: str | None) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def resolve(self, app_state: Any) -> ResolvedDetectionConfig:
        return await resolve_detection_config(self._db, app_state, self._tenant_id)

    @classmethod
    def invalidate(cls, tenant_id: str | None = None) -> None:
        """Force cache invalidation for a tenant (or platform if None)."""
        _cache.pop(tenant_id or "", None)
