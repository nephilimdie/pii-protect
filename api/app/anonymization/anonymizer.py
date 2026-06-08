import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.detection.detector_registry import DetectorRegistry
from app.detection.entities import PiiEntity, MappingEntry
from app.detection.entity_merger import EntityMerger
from app.detection.token_generator import TokenGenerator
from app.anonymization.anonymization_result import AnonymizationResult

_WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_PASSWORD_EXTRA = frozenset("!@#$%^&*()+=[]{}|;:<>?/\\~`")
_PASSWORD_TYPES = frozenset({"SECRET", "PASSWORD"})


_HONORIFIC_RE = re.compile(
    r"(?:Dr\.?|Dott\.?(?:ssa)?|Avv\.?|Ing\.?|Prof\.?|Sig\.?(?:ra)?|Arch\.?|Rag\.?|Geom\.?)\s+$",
    re.IGNORECASE,
)

# Compiled reclassification rules loaded from DB at startup / on change.
# Each entry: (context_re | None, entity_re | None, from_type, to_type | None, context_window)
# context_re  — matched against the N chars BEFORE the entity; None = skip check
# entity_re   — matched against the entity text itself;           None = skip check
# Both present → both must match (AND logic)
_reclassify_rules: list[tuple[re.Pattern | None, re.Pattern | None, str, str | None, int]] = []


def set_reclassify_rules(rules: list[dict]) -> None:
    global _reclassify_rules
    compiled = []
    for r in rules:
        try:
            ctx_pat = r.get("context_pattern")
            ent_pat = r.get("entity_pattern")
            if not ctx_pat and not ent_pat:
                continue
            compiled.append((
                re.compile(ctx_pat) if ctx_pat else None,
                re.compile(ent_pat) if ent_pat else None,
                r["from_type"],
                r.get("to_type"),
                int(r.get("context_window", 60)),
            ))
        except re.error:
            pass
    _reclassify_rules = compiled


def _reclassify(entity: "PiiEntity", text: str) -> "PiiEntity | None":
    for context_re, entity_re, from_type, to_type, window_size in _reclassify_rules:
        if entity.pii_type != from_type:
            continue
        if context_re is not None:
            window = text[max(0, entity.start - window_size):entity.start]
            if not context_re.search(window):
                continue
        if entity_re is not None:
            if not entity_re.search(entity.text):
                continue
        if to_type is None:
            return None
        return PiiEntity(
            start=entity.start, end=entity.end,
            pii_type=to_type, text=entity.text, score=entity.score,
            source=entity.source,
        )
    return entity


# Kinship/relational prefixes that ML models include in PERSON entities by mistake
_KINSHIP_PREFIX_RE = re.compile(
    r"^(?:(?:mio|mia|suo|sua|il|la|lo|i|gli|le)\s+)?"
    r"(?:moglie|marito|figlio|figlia|sorella|fratello|padre|madre|"
    r"nonno|nonna|nipote|zio|zia|cugino|cugina|compagno|compagna|"
    r"genero|nuora|cognato|cognata)\s+",
    re.IGNORECASE,
)


def _snap_to_word_boundary(text: str, entity: PiiEntity) -> PiiEntity:
    start, end = entity.start, entity.end

    # Strip leading whitespace from entity (BPE tokens often include preceding space)
    while start < end and text[start] in " \t":
        start += 1

    # Expand right if entity ends mid-word
    extra = _PASSWORD_EXTRA if entity.pii_type in _PASSWORD_TYPES else frozenset()
    while end < len(text) and (text[end] in _WORD_CHARS or text[end] in extra):
        end += 1

    # Expand left only if entity starts mid-word (first char is a word char)
    if start < len(text) and text[start] in _WORD_CHARS:
        while start > 0 and text[start - 1] in _WORD_CHARS:
            start -= 1

    if entity.pii_type == "PERSON":
        # Absorb a preceding honorific (Dr., Avv., etc.)
        if start > 0:
            prefix = text[max(0, start - 15):start]
            m = _HONORIFIC_RE.search(prefix)
            if m:
                start = start - (len(prefix) - m.start())
        # Strip leading kinship/relational term included by ML models
        m = _KINSHIP_PREFIX_RE.match(text[start:end])
        if m:
            start = start + m.end()

    if start >= end:
        return entity
    if start == entity.start and end == entity.end:
        return entity
    return PiiEntity(start=start, end=end, pii_type=entity.pii_type, text=text[start:end], score=entity.score)


def _is_valid_entity(entity: PiiEntity, denylist: dict[str, dict]) -> bool:
    if entity.pii_type == "PERSON":
        if "\n" in entity.text or "\r" in entity.text:
            return False
    bucket = denylist.get(entity.pii_type, {})
    text_lower = entity.text.lower().strip()
    # exact_word: strip honorifics, check single word
    exact = bucket.get("exact", set())
    if exact:
        clean = _HONORIFIC_RE.sub("", entity.text.strip()).strip()
        words = clean.lower().split()
        if len(words) == 1 and words[0].rstrip(".,:;") in exact:
            return False
    # contains: reject if entity text contains any denied substring
    for phrase in bucket.get("contains", []):
        if phrase in text_lower:
            return False
    return True


class DetectionResult:
    """Raw detection result before token assignment — used by the new policy-aware router."""
    def __init__(self, entities: list[PiiEntity]) -> None:
        self.entities = entities


class PiiAnonymizer:
    def __init__(self, registry: DetectorRegistry, denylist: dict[str, dict] | None = None) -> None:
        self._registry = registry
        self._merger = EntityMerger()
        self._denylist = denylist or {}

    def detect_only(self, text: str, context_id: str, context_type: str, language: str = "it") -> DetectionResult:
        """Run detection pipeline and return merged/reclassified entities without token assignment.
        Called by the policy-aware anonymize router so it can filter by protect/keep lists."""
        detectors = self._registry.get_ordered()
        all_entities: list[PiiEntity] = []

        with ThreadPoolExecutor(max_workers=len(detectors) or 1) as pool:
            futures = {pool.submit(d.detect, text, language): d for d in detectors}
            for future in as_completed(futures):
                all_entities.extend(future.result())

        merged = self._merger.merge(all_entities, text)
        reclassified = [r for e in merged if (r := _reclassify(e, text)) is not None]
        snapped = [_snap_to_word_boundary(text, e)
                   for e in reclassified if _is_valid_entity(e, self._denylist)]
        snapped = self._merger.merge(snapped, text)
        return DetectionResult(entities=snapped)

    def anonymize(self, text: str, context_id: str, context_type: str, language: str = "it") -> AnonymizationResult:
        detectors = self._registry.get_ordered()
        all_entities: list[PiiEntity] = []

        with ThreadPoolExecutor(max_workers=len(detectors) or 1) as pool:
            futures = {pool.submit(d.detect, text, language): d for d in detectors}
            for future in as_completed(futures):
                all_entities.extend(future.result())

        merged = self._merger.merge(all_entities, text)

        # Reclassify entities based on surrounding context (e.g. PERSON → ACCOUNT after "username:")
        reclassified = []
        for e in merged:
            r = _reclassify(e, text)
            if r is not None:
                reclassified.append(r)

        snapped = [_snap_to_word_boundary(text, e) for e in reclassified if _is_valid_entity(e, self._denylist)]
        # Re-merge after snapping in case boundaries now overlap
        snapped = self._merger.merge(snapped, text)

        generator = TokenGenerator()
        # Pass 1: assign tokens in left-to-right text order so [TYPE_1] is
        # the leftmost occurrence, [TYPE_2] the next, etc.
        stable_map: dict[str, str] = {}
        for entity in snapped:
            key = entity.text.lower().strip()
            if key not in stable_map:
                stable_map[key] = generator.next_token(entity.pii_type)

        # Pass 2: replace from right to preserve char offsets
        mappings: list[MappingEntry] = []
        result = text
        for entity in reversed(snapped):
            key = entity.text.lower().strip()
            token = stable_map[key]
            result = result[:entity.start] + token + result[entity.end:]
            mappings.append(MappingEntry(
                token=token,
                original=entity.text,
                pii_type=entity.pii_type,
                start=entity.start,
                end=entity.end,
                score=entity.score,
            ))

        return AnonymizationResult(anonymized_text=result, mappings=mappings)
