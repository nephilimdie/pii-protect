from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.plugins.base import BasePlugin
from app.plugins.manifest import PluginManifest
from app.plugins.registry import PluginRegistry


class PluginLoader:
    """Discover and explicitly load validated plugins from one directory."""

    def __init__(self, directory: str | Path, registry: PluginRegistry) -> None:
        self._directory = Path(directory).resolve()
        self._registry = registry

    def manifests(self) -> list[PluginManifest]:
        if not self._directory.is_dir():
            return []
        result = []
        for manifest_path in sorted(self._directory.glob("*/plugin.json")):
            result.append(PluginManifest.from_file(manifest_path))
        return result

    def load_all(self) -> list[str]:
        loaded = []
        for manifest in self.manifests():
            self._load(manifest)
            loaded.append(manifest.name)
        return loaded

    def _load(self, manifest: PluginManifest) -> None:
        module_name, class_name = manifest.entrypoint.split(":", 1)
        plugin_dir = self._directory / manifest.name
        module_path = (plugin_dir / (module_name.replace(".", "/") + ".py")).resolve()
        if plugin_dir not in module_path.parents or not module_path.is_file():
            raise ValueError(f"plugin_entrypoint_outside_plugin:{manifest.name}")
        spec = importlib.util.spec_from_file_location(f"pii_plugin_{manifest.name}", module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"plugin_import_failed:{manifest.name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        plugin = getattr(module, class_name, None)
        if not isinstance(plugin, type) or not issubclass(plugin, BasePlugin):
            raise ValueError(f"plugin_class_invalid:{manifest.name}")
        self._registry.register(plugin())
