from __future__ import annotations
import dataclasses
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

from app.detection.detector_registry import DetectorRegistry
from app.detection.entities import PiiEntity, MappingEntry
from app.detection.entity_merger import EntityMerger
from app.detection.token_generator import TokenGenerator
from app.anonymization.anonymization_result import AnonymizationResult

def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_" or unicodedata.category(char).startswith("M")

_PASSWORD_EXTRA = frozenset("!@#$%^&*()+=[]{}|;:<>?/\\~`")
_PASSWORD_TYPES = frozenset({"SECRET", "PASSWORD"})


# Leading courtesy/professional titles (optionally after an article). Abbreviations need their dot
# so names like "Arch" or "Ing" stay intact; titles are context, not identity, and stay in clear.
_HONORIFIC_PREFIX_RE = re.compile(
    r"^(?:(?:il|la|lo|gli|le|i)\s+)?(?:(?:(?:sig|dott|dr|prof)\.(?:ssa|r[aei]|na)\.?|avv\.ta\.?"
    r"|(?:sigg?|dott|dr|avv|ing|geom|rag|prof|arch)\.|notaio|signor[ae]?|dottor(?:essa)?|avvocato"
    r"|ingegnere|professor(?:e|essa)|architetto|geometra|ragioniere)\s+)+",
    re.IGNORECASE,
)

# Italian form-field labels next to a value ("Mario Rossi, C.F. ...", "Rossi nato a ..."). ML layers tag
# them as PERSON fragments that the merger then glues onto the real name; they are never PII themselves.
_FIELD_LABEL = (
    r"(?<![^\W_])(?:c\.\s?f\.?|cf|cod(?:ice|\.)\s*fisc(?:ale|\.)?|p\.?\s?iva|partita\s+iva|nat[oa]|residente"
    r"|domiciliat[oa]|tel(?:efono|\.)|cell(?:ulare|\.)|e-?mail|pec|n\.|nr\.|matr(?:icola|\.))(?![^\W_])"
)
_SEPARATORS = r"[\s,;:.\-–—]"
_LABEL_PREFIX_RE = re.compile(rf"^(?:{_FIELD_LABEL}{_SEPARATORS}*)+", re.IGNORECASE)
_PERSON_SUFFIX_RE = re.compile(rf"(?:{_SEPARATORS}|{_FIELD_LABEL})+$", re.IGNORECASE)

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


def _snap_to_word_boundary(text: str, entity: PiiEntity) -> PiiEntity | None:
    start, end = entity.start, entity.end

    # Strip leading whitespace from entity (BPE tokens often include preceding space)
    while start < end and text[start] in " \t":
        start += 1

    # Expand right if entity ends mid-word
    extra = _PASSWORD_EXTRA if entity.pii_type in _PASSWORD_TYPES else frozenset()
    while end < len(text) and (_is_word_char(text[end]) or text[end] in extra):
        end += 1

    # Expand left only if entity starts mid-word (first char is a word char)
    if start < len(text) and _is_word_char(text[start]):
        while start > 0 and _is_word_char(text[start - 1]):
            start -= 1

    if entity.pii_type == "PERSON":
        # Strip leading titles ("sig.ra", "avv.") and kinship terms ML models include in the span
        for prefix_re in (_KINSHIP_PREFIX_RE, _HONORIFIC_PREFIX_RE):
            if m := prefix_re.match(text[start:end]):
                start += m.end()
        # Strip trailing punctuation and field labels ("Mario Rossi, C.F." -> "Mario Rossi")
        if m := _PERSON_SUFFIX_RE.search(text[start:end]):
            end = start + m.start()
    if entity.pii_type not in _PASSWORD_TYPES and (m := _LABEL_PREFIX_RE.match(text[start:end])):
        start += m.end()

    if start >= end:
        return None  # span was only a title/label: nothing left to protect
    if start == entity.start and end == entity.end:
        return entity
    return dataclasses.replace(entity, start=start, end=end, text=text[start:end])


def _snap_all(text: str, entities: list[PiiEntity]) -> list[PiiEntity]:
    """Why: ML spans carry stray whitespace, titles and field labels that must go before merging,
    or the merger glues label fragments onto adjacent names.
    What: snaps every entity to word boundaries and drops those that were only a title/label.
    Test: [PERSON ' C.F.'] -> []; [PERSON 'Mario Rossi, C.F.'] -> [PERSON 'Mario Rossi'].
    """
    return [snapped for e in entities if (snapped := _snap_to_word_boundary(text, e)) is not None]


def _is_valid_entity(entity: PiiEntity, denylist: dict[str, dict]) -> bool:
    if entity.pii_type == "PERSON":
        if "\n" in entity.text or "\r" in entity.text:
            return False
    bucket = denylist.get(entity.pii_type, {})
    text_lower = entity.text.lower().strip()
    # exact_word: strip honorifics, check single word
    exact = bucket.get("exact", set())
    if exact:
        clean = _HONORIFIC_PREFIX_RE.sub("", entity.text.strip()).strip()
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
        layer_configs: dict[str, dict] | None = None,
    ) -> None:
        self._registry = registry
        self._merger = EntityMerger()
        self._denylist = denylist or {}
        self._tenant_enabled_layers = None if enabled_layers is None else frozenset(enabled_layers)
        self._enabled_layers = self._tenant_enabled_layers
        self._layer_configs = layer_configs or {}
        if reclassification_rules is not None:
            self._reclassify_rules = _compile_rules(reclassification_rules)
        else:
            self._reclassify_rules = None
        # Tenant-effective patterns/context; None = use registry's built-in detectors as-is
        self._regex_patterns = regex_patterns
        self._presidio_context = presidio_context

    def restrict_layers(self, layers: list[str] | None) -> None:
        """Select each item's layers from the tenant baseline, not the previous item."""
        if layers is None:
            self._enabled_layers = self._tenant_enabled_layers
            return
        selected = set(layers)
        self._enabled_layers = selected if self._tenant_enabled_layers is None else self._tenant_enabled_layers & selected

    def _run_detectors(self, text: str, language: str) -> list[PiiEntity]:
        """Run all detectors, applying per-tenant regex patterns, presidio context, and layer configs."""
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
                cfg = self._layer_configs.get(d.layer_name)
                if isinstance(d, ItalianRegexDetector) and self._regex_patterns is not None:
                    continue  # replaced by tenant-effective patterns below
                if isinstance(d, PresidioDetector):
                    ctx = self._presidio_context if self._presidio_context is not None else None
                    futures[pool.submit(d.detect, text, language, ctx, cfg)] = d
                else:
                    futures[pool.submit(d.detect, text, language, cfg)] = d

            if self._regex_patterns is not None and (
                self._enabled_layers is None or "regex" in self._enabled_layers
            ):
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
        # Snap raw spans first so label-only fragments are dropped before the merger can join them
        merged = self._merger.merge(_snap_all(text, self._run_detectors(text, language)), text)
        # Reclassify entities based on surrounding context (e.g. PERSON → ACCOUNT after "username:")
        reclassified = [r for e in merged if (r := self._reclassify_entity(e, text)) is not None]
        valid = [e for e in reclassified if _is_valid_entity(e, self._denylist)]
        # Re-merge after snapping in case boundaries now overlap
        return DetectionResult(entities=self._merger.merge(_snap_all(text, valid), text))

    def anonymize(self, text: str, context_id: str, context_type: str, language: str = "it") -> AnonymizationResult:
        snapped = self.detect_only(text, context_id, context_type, language).entities

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
