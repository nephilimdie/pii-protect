from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    name: str  # override in subclass
    version: str = "0.1.0"

    @abstractmethod
    async def on_anonymize(self, text: str, entities: list[Any]) -> list[Any]:
        """Called after entity detection, before mapping. Can modify/add entities."""
        ...

    @abstractmethod
    async def on_deanonymize(self, text: str, mapping: dict[str, str]) -> str:
        """Called after token replacement. Can post-process output."""
        ...

    def metadata(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}
