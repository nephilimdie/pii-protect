from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.base import BasePlugin


class PluginRegistry:
    _plugins: list["BasePlugin"] = []

    @classmethod
    def register(cls, plugin: "BasePlugin") -> None:
        cls._plugins.append(plugin)

    @classmethod
    def all(cls) -> list["BasePlugin"]:
        return list(cls._plugins)

    @classmethod
    def clear(cls) -> None:
        cls._plugins.clear()


plugin_registry = PluginRegistry()
