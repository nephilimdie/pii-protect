from __future__ import annotations
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

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


def _compile_rules(rules: list[dict]) -> list:
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
    return compiled


def set_reclassify_rules(rules: list[dict]) -> None:
    global _reclassify_rules
    _reclassify_rules = _compile_rules(rules)



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
    def __init__(
        self,
        registry: DetectorRegistry,
        denylist: dict[str, dict] | None = None,
        reclassification_rules: list[dict] | None = None,
        regex_patterns: list[dict] | None = None,
        presidio_context: dict[str, list[str]] | None = None,
        enabled_layers: set[str] | None = None,
    ) -> None:
        self._registry = registry
        self._merger = EntityMerger()
        self._denylist = denylist or {}
        self._enabled_layers = enabled_layers
        if reclassification_rules is not None:
            self._reclassify_rules = _compile_rules(reclassification_rules)
        else:
            self._reclassify_rules = None
        # Tenant-effective patterns/context; None = use registry's built-in detectors as-is
        self._regex_patterns = regex_patterns
        self._presidio_context = presidio_context

    def _run_detectors(self, text: str, language: str) -> list[PiiEntity]:
        """Run all detectors, applying per-tenant regex patterns and presidio context when set."""
        from app.detection.layers.regex_layer import ItalianRegexDetector
        from app.detection.layers.presidio_layer import PresidioDetector

        detectors = [
            detector for detector in self._registry.get_ordered()
            if self._enabled_layers is None or detector.layer_name in self._enabled_layers
        ]
        all_entities: list[PiiEntity] = []

        with ThreadPoolExecutor(max_workers=max(len(detectors) + 1, 1)) as pool:
            futures = {}
            for d in detectors:
                if isinstance(d, ItalianRegexDetector) and self._regex_patterns is not None:
                    continue  # replaced by tenant-effective patterns below
                if isinstance(d, PresidioDetector) and self._presidio_context is not None:
                    futures[pool.submit(d.detect, text, language, self._presidio_context)] = d
                else:
                    futures[pool.submit(d.detect, text, language)] = d

            if self._regex_patterns is not None:
                patterns = [SimpleNamespace(**p) for p in self._regex_patterns]
                tenant_regex = ItalianRegexDetector(patterns)
                futures[pool.submit(tenant_regex.detect, text, language)] = tenant_regex

            for future in as_completed(futures):
                all_entities.extend(future.result())

        return all_entities

    def _reclassify_entity(self, entity: PiiEntity, text: str) -> "PiiEntity | None":
        rules = self._reclassify_rules if self._reclassify_rules is not None else _reclassify_rules
        for context_re, entity_re, from_type, to_type, window_size in rules:
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
                text=entity.text,
                start=entity.start,
                end=entity.end,
                pii_type=to_type,
                score=entity.score,
                source=getattr(entity, "source", "reclassification"),
            )
        return entity

    def detect_only(self, text: str, context_id: str, context_type: str, language: str = "it") -> DetectionResult:
        """Run detection pipeline and return merged/reclassified entities without token assignment.
        Called by the policy-aware anonymize router so it can filter by protect/keep lists."""
        all_entities: list[PiiEntity] = self._run_detectors(text, language)

        merged = self._merger.merge(all_entities, text)
        reclassified = [r for e in merged if (r := self._reclassify_entity(e, text)) is not None]
        snapped = [_snap_to_word_boundary(text, e)
                   for e in reclassified if _is_valid_entity(e, self._denylist)]
        snapped = self._merger.merge(snapped, text)
        return DetectionResult(entities=snapped)

    def anonymize(self, text: str, context_id: str, context_type: str, language: str = "it") -> AnonymizationResult:
        all_entities: list[PiiEntity] = self._run_detectors(text, language)

        merged = self._merger.merge(all_entities, text)

        # Reclassify entities based on surrounding context (e.g. PERSON → ACCOUNT after "username:")
        reclassified = []
        for e in merged:
            r = self._reclassify_entity(e, text)
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
