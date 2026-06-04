import re
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity
from app.detection.models import RegexPattern


class CompiledPattern:
    def __init__(self, pii_type: str, pattern: re.Pattern, capture_group: int) -> None:
        self.pii_type = pii_type
        self.pattern = pattern
        self.capture_group = capture_group


class ItalianRegexDetector(DetectorContract):
    def __init__(self, patterns: list[RegexPattern]) -> None:
        self._compiled: list[CompiledPattern] = _compile(patterns)

    def reload(self, patterns: list[RegexPattern]) -> None:
        self._compiled = _compile(patterns)

    @property
    def layer_name(self) -> str:
        return "regex"

    @property
    def priority(self) -> int:
        return 30

    def detect(self, text: str, language: str = "it") -> list[PiiEntity]:
        entities: list[PiiEntity] = []
        for cp in self._compiled:
            for match in cp.pattern.finditer(text):
                try:
                    matched_text = match.group(cp.capture_group)
                    start = match.start(cp.capture_group)
                    end = match.end(cp.capture_group)
                except IndexError:
                    continue
                if matched_text:
                    entities.append(PiiEntity(
                        start=start,
                        end=end,
                        pii_type=cp.pii_type,
                        text=matched_text,
                        score=1.0,
                    ))
        return entities


def _compile(patterns: list[RegexPattern]) -> list[CompiledPattern]:
    result = []
    for p in patterns:
        flag_value = 0
        for flag_name in p.flags.split(","):
            flag_name = flag_name.strip()
            if flag_name == "IGNORECASE":
                flag_value |= re.IGNORECASE
            elif flag_name == "MULTILINE":
                flag_value |= re.MULTILINE
            elif flag_name == "DOTALL":
                flag_value |= re.DOTALL
        try:
            compiled = re.compile(p.pattern, flag_value)
            result.append(CompiledPattern(p.pii_type, compiled, p.capture_group))
        except re.error:
            pass
    return result
