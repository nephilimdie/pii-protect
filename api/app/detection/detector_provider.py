from app.config import Settings
from app.detection.detector_registry import DetectorRegistry
from app.detection.layers.regex_layer import ItalianRegexDetector
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.detection.models import RegexPattern


class DetectorProvider:
    """Builds a DetectorRegistry from config. Add new layers here only."""

    def __init__(self, settings: Settings, regex_patterns: list[RegexPattern] | None = None) -> None:
        self._settings = settings
        self._regex_patterns = regex_patterns or []

    def build(self) -> DetectorRegistry:
        registry = DetectorRegistry()
        lc = self._settings.detection_layers

        if lc.get("presidio", {}).get("enabled", True):
            registry.register(PresidioDetector())

        if lc.get("privacy_filter", {}).get("enabled", True):
            registry.register(PrivacyFilterDetector(model=self._settings.privacy_filter_model))

        if lc.get("ai4privacy", {}).get("enabled", True):
            registry.register(Ai4PrivacyDetector(model=self._settings.ai4privacy_model))

        if lc.get("regex", {}).get("enabled", True):
            registry.register(ItalianRegexDetector(self._regex_patterns))

        return registry
