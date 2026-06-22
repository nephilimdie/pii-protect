"""Reads per-layer ML configuration from the layer_settings table.

Schema: layer_settings(id, tenant_id nullable, layer, config JSONB, updated_at)
- tenant_id IS NULL  → global default override
- tenant_id IS NOT NULL → tenant-specific override
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection import layer_config as lc


class LayerSettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all_global(self) -> dict[str, dict]:
        """Return {layer: config_dict} for tenant_id IS NULL rows."""
        rows = await self._db.execute(
            text("SELECT layer, config FROM layer_settings WHERE tenant_id IS NULL")
        )
        return {row.layer: row.config for row in rows}

    async def get_all_tenant(self, tenant_id: str) -> dict[str, dict]:
        """Return {layer: config_dict} for a specific tenant."""
        rows = await self._db.execute(
            text("SELECT layer, config FROM layer_settings WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        return {row.layer: row.config for row in rows}

    async def get_effective(self, tenant_id: str | None) -> dict[str, dict]:
        """Return effective config for every layer: defaults → global override → tenant override."""
        global_rows = await self.get_all_global()
        tenant_rows = await self.get_all_tenant(tenant_id) if tenant_id else {}
        return {
            layer: lc.effective(layer, tenant_rows.get(layer), global_rows.get(layer))
            for layer in lc.ALL_LAYERS
        }

    async def upsert(self, tenant_id: str | None, layer: str, config: dict) -> None:
        """Insert or update a row. tenant_id=None means global."""
        existing = await self._db.execute(
            text("SELECT id FROM layer_settings WHERE tenant_id IS NOT DISTINCT FROM :tid AND layer = :layer"),
            {"tid": tenant_id, "layer": layer},
        )
        row = existing.fetchone()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cfg_json = json.dumps(config)
        if row:
            await self._db.execute(
                text("UPDATE layer_settings SET config = cast(:cfg AS jsonb), updated_at = :now WHERE id = :id"),
                {"cfg": cfg_json, "now": now, "id": row.id},
            )
        else:
            await self._db.execute(
                text(
                    "INSERT INTO layer_settings (id, tenant_id, layer, config, updated_at) "
                    "VALUES (:id, :tid, :layer, cast(:cfg AS jsonb), :now)"
                ),
                {"id": str(uuid.uuid4()), "tid": tenant_id, "layer": layer, "cfg": cfg_json, "now": now},
            )
        await self._db.commit()

    async def delete(self, tenant_id: str | None, layer: str) -> bool:
        """Delete a row (revert to global/defaults). Returns True if deleted."""
        result = await self._db.execute(
            text(
                "DELETE FROM layer_settings WHERE tenant_id IS NOT DISTINCT FROM :tid AND layer = :layer"
            ),
            {"tid": tenant_id, "layer": layer},
        )
        await self._db.commit()
        return result.rowcount > 0
