from abc import ABC, abstractmethod
from app.detection.entities import PiiEntity


class DetectorContract(ABC):

    @property
    @abstractmethod
    def layer_name(self) -> str:
        """Unique identifier for this detection layer."""

    @property
    @abstractmethod
    def priority(self) -> int:
        """Execution order — lower runs first. Regex=10, Presidio=20, PrivacyFilter=30."""

    @abstractmethod
    def detect(self, text: str) -> list[PiiEntity]:
        """Detect PII entities in text. Must not raise — return [] on failure."""

    def is_available(self) -> bool:
        """Return False if model/dependency not loaded. Default True."""
        return True
