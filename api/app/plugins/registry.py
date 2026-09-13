from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.base import BasePlugin


class PluginRegistry:
    _plugins: list["BasePlugin"] = []

    @classmethod
    def register(cls, plugin: "BasePlugin") -> None:
        if not any(item.name == plugin.name for item in cls._plugins):
            cls._plugins.append(plugin)

    @classmethod
    def all(cls) -> list["BasePlugin"]:
        return list(cls._plugins)

    @classmethod
    def clear(cls) -> None:
        cls._plugins.clear()

    @classmethod
    def unregister(cls, name: str) -> bool:
        before = len(cls._plugins)
        cls._plugins = [plugin for plugin in cls._plugins if plugin.name != name]
        return len(cls._plugins) != before

    @classmethod
    async def anonymize_hooks(cls, text: str, entities: list) -> list:
        for plugin in cls._plugins:
            entities = await plugin.on_anonymize(text, entities)
        return entities

    @classmethod
    async def deanonymize_hooks(cls, text: str, mapping: dict[str, str]) -> str:
        for plugin in cls._plugins:
            text = await plugin.on_deanonymize(text, mapping)
        return text


plugin_registry = PluginRegistry()
