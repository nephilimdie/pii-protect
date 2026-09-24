import re
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity
from app.detection.models import RegexPattern


_NAME_WORD = r"[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+"
_NAME_PARTICLE = r"(?:[Dd]e|[Dd]el|[Dd]ella|[Dd]i|[Dd]a|[Vv]an|[Vv]on|[Dd]er|[Dd]en|[Ll]a|[Ll]e)"
_COMPOUND_NAME = re.compile(
    rf"\b(?:{_NAME_WORD}\s+{_NAME_PARTICLE}\s+{_NAME_WORD}|"
    rf"{_NAME_WORD}\s+{_NAME_WORD})\b"
)
_ABBREVIATED_NAME = re.compile(rf"\b[A-ZÀ-ÖØ-Ý]\.\s+{_NAME_WORD}\b")
_ADDRESS = re.compile(
    (
        rf"\b(?:via|viale|piazza|corso|largo|strada)\s+"
        rf"{_NAME_WORD}(?:[\s'-]+[A-Za-zÀ-ÖØ-öø-ÿ]+){{0,5}}\s+"
        rf"\d{{1,5}}[A-Za-z]?"
        rf"(?:,\s*\d{{5}}\s+{_NAME_WORD}(?:[\s'-]+[A-Za-zÀ-ÖØ-öø-ÿ]+){{0,3}})?"
    ),
    re.IGNORECASE,
)
_PERSON_CONTEXT = re.compile(
    r"(?:\b(?:sig(?:nora)?|sig\.ra|mr|ms|referente|paziente|cliente|utente|"
    r"nome|nato|nata|intestat\w*)\b|\bintestat\w*\s+a)\s*[:]?\s*$",
    re.IGNORECASE,
)


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

    def detect(self, text: str, language: str = "it", layer_config: dict | None = None) -> list[PiiEntity]:
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
                        source="regex",
                    ))
        entities.extend(_detect_structured_entities(text))
        return entities


def _detect_structured_entities(text: str) -> list[PiiEntity]:
    """Detect high-signal names and addresses without broad capitalized-word rules."""
    entities: list[PiiEntity] = []
    for pattern in (_ABBREVIATED_NAME, _COMPOUND_NAME):
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 48):match.start()]
            if not _PERSON_CONTEXT.search(prefix):
                continue
            entities.append(PiiEntity(
                start=match.start(), end=match.end(), pii_type="PERSON",
                text=match.group(), score=1.0, source="regex",
            ))

    for match in _ADDRESS.finditer(text):
        entities.append(PiiEntity(
            start=match.start(), end=match.end(), pii_type="ADDRESS",
            text=match.group(), score=1.0, source="regex",
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
