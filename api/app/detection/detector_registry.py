from app.detection.contracts.detector_contract import DetectorContract


class DetectorRegistry:
    def __init__(self) -> None:
        self._detectors: list[DetectorContract] = []

    def register(self, detector: DetectorContract) -> None:
        self._detectors.append(detector)

    def get_ordered(self) -> list[DetectorContract]:
        return sorted(
            [d for d in self._detectors if d.is_available()],
            key=lambda d: d.priority,
        )

    def get_by_name(self, name: str) -> DetectorContract | None:
        return next((d for d in self._detectors if d.layer_name == name), None)

    def names(self) -> list[str]:
        return [d.layer_name for d in self.get_ordered()]
