import json

import pytest

from app.plugins.loader import PluginLoader
from app.plugins.registry import PluginRegistry


def test_loader_validates_and_loads_plugin(tmp_path) -> None:
    plugin_dir = tmp_path / "plugins" / "demo.plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "demo.plugin",
        "version": "1.0.0",
        "entrypoint": "plugin:DemoPlugin",
        "permissions": ["detect"],
    }))
    (plugin_dir / "plugin.py").write_text(
        "from app.plugins.base import BasePlugin\n"
        "class DemoPlugin(BasePlugin):\n"
        "    name = 'demo.plugin'\n"
        "    async def on_anonymize(self, text, entities): return entities\n"
        "    async def on_deanonymize(self, text, mapping): return text\n"
    )
    registry = PluginRegistry()
    loaded = PluginLoader(tmp_path / "plugins", registry).load_all()

    assert loaded == ["demo.plugin"]
    assert registry.all()[0].metadata()["name"] == "demo.plugin"


def test_loader_rejects_invalid_manifest(tmp_path) -> None:
    plugin_dir = tmp_path / "plugins" / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({"name": "Bad Name"}))

    with pytest.raises(ValueError, match="invalid_plugin_name"):
        PluginLoader(tmp_path / "plugins", PluginRegistry()).manifests()
