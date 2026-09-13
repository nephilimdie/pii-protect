from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    entrypoint: str
    permissions: tuple[str, ...]
    compatibility: str

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid_plugin_manifest:{path}") from exc
        name = data.get("name")
        version = data.get("version")
        entrypoint = data.get("entrypoint")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", name):
            raise ValueError("invalid_plugin_name")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("invalid_plugin_version")
        if not isinstance(entrypoint, str) or entrypoint.count(":") != 1:
            raise ValueError("invalid_plugin_entrypoint")
        permissions = data.get("permissions", [])
        if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
            raise ValueError("invalid_plugin_permissions")
        compatibility = data.get("compatibility", ">=1.0,<2.0")
        if not isinstance(compatibility, str):
            raise ValueError("invalid_plugin_compatibility")
        return cls(name, version, entrypoint, tuple(permissions), compatibility)

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "entrypoint": self.entrypoint,
            "permissions": list(self.permissions),
            "compatibility": self.compatibility,
        }
