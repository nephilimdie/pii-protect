"""Rizzo-PII layer: Italian mmBERT token classifier (rizzoaiacademy/rizzo-pii-0.3B, MIT).

Why: an Italian-specific model trained with case augmentation recovers what our other layers miss
(ALL-CAPS names, form-field birth places, table-cell identifiers); held-out v1 leak 8.8% vs 17.3%.
What: loads the pinned weights from a local directory baked into the image at build time (no
runtime download), runs them on 120-word chunks with a 20-word overlap and "simple" aggregation
(the model's own inference recipe), maps the 22 Rizzo tags to Pseudora types, fuses adjacent
address parts, widens spans that cut a word, and drops non-PII tags (AMOUNT, ORG, TIME, AGE, GENDER).
Inference idea and tag set follow https://github.com/Rizzo-AI-Academy/rizzo-pii (MIT,
Copyright (c) 2026 Simone Rizzo - Rizzo AI Academy); this module is a reimplementation, no code copied.
Test: tests/unit/test_rizzo_layer.py drives detect() with a fake pipeline (chunking, mapping, fusion, widening).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

logger = logging.getLogger(__name__)

LAYER = "rizzo"
MAX_WORDS, OVERLAP = 120, 20
_MIN_SCORE = 0.5
LABEL_MAP: dict[str, str | None] = {
    "FULLNAME": "PERSON", "CF": "FISCAL_CODE", "PIVA": "VAT_NUMBER", "IBAN": "IBAN",
    "CREDITCARDNUMBER": "CREDIT_CARD", "EMAIL": "EMAIL", "TELEPHONENUM": "PHONE",
    "STREET": "ADDRESS", "BUILDINGNUM": "ADDRESS", "ZIPCODE": "ADDRESS", "CITY": "ADDRESS", "PROVINCE": "ADDRESS",
    "DATE": "DATE", "ID_DOC": "IDENTITY_CARD", "TARGA": "TARGA", "CATASTO": "CADASTRAL_REF", "DOCID": "PRACTICE_ID",
    "AMOUNT": None, "ORG": None, "TIME": None, "AGE": None, "GENDER": None,
}
TYPES = sorted({t for t in LABEL_MAP.values() if t})
_ADDRESS_GLUE = re.compile(r"[ ,\-–/]{0,3}")
# a stand-alone address part this short or numeric is a house number/CAP/province without a street
_LONE_ADDRESS_PART = re.compile(r"[\d\s/]+[A-Za-z]?|[A-Z]{2}")


def chunks(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP) -> list[tuple[str, int]]:
    """Why: the model was trained on ~120-word windows; longer input degrades and truncates.
    What: [(slice, offset)] of whole-word windows, consecutive windows sharing `overlap` words.
    Test: chunks("a b c", 2, 1) == [("a b", 0), ("b c", 2)].
    """
    words = list(re.finditer(r"\S+", text))
    out, i, step = [], 0, max(1, max_words - overlap)
    while i < len(words):
        block = words[i:i + max_words]
        out.append((text[block[0].start():block[-1].end()], block[0].start()))
        if i + max_words >= len(words):
            break
        i += step
    return out


def _widen(text: str, start: int, end: int) -> tuple[int, int]:
    while start > 0 and text[start - 1].isalnum() and text[start].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum() and text[end - 1].isalnum():
        end += 1
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _fuse(text: str, spans: list[tuple[int, int, str, float]]) -> list[tuple[int, int, str, float]]:
    """Overlapping spans of one type (chunk overlap) and address parts on one line become one span."""
    out: list[list] = []
    for s, e, t, sc in sorted(spans):
        if out and out[-1][2] == t and (s < out[-1][1] or (
                t == "ADDRESS" and _ADDRESS_GLUE.fullmatch(text[out[-1][1]:s]) and "\n" not in text[out[-1][1]:s])):
            out[-1][1], out[-1][3] = max(out[-1][1], e), max(out[-1][3], sc)
        elif out and s < out[-1][1]:
            continue  # cross-type overlap from the window overlap: keep the first
        else:
            out.append([s, e, t, sc])
    return [tuple(x) for x in out]


class RizzoDetector(DetectorContract):
    """Why/What: see module docstring. Test: see tests/unit/test_rizzo_layer.py."""

    _pipeline = None

    @property
    def layer_name(self) -> str:
        return LAYER

    @property
    def priority(self) -> int:
        return 27

    def is_available(self) -> bool:
        return self._pipeline is not None

    @classmethod
    def preload(cls, model_dir: str, revision: str) -> None:
        """Why: weights are pinned and baked into the image; a different or missing copy must be loud.
        What: loads a token-classification pipeline from model_dir; logs an error (layer unavailable,
        readiness 503) when the directory is missing or its REVISION file names another commit.
        Test: preload("/nonexistent", "x") leaves is_available() False.
        """
        path = Path(model_dir)
        if not (path / "config.json").is_file():
            logger.error("Rizzo-PII model not found in %s (expected revision %s)", model_dir, revision)
            return
        found = (path / "REVISION").read_text().strip() if (path / "REVISION").is_file() else "unknown"
        if found not in (revision, "unknown"):
            logger.error("Rizzo-PII model in %s is revision %s, expected %s", model_dir, found, revision)
            return
        try:
            from transformers import pipeline as hf_pipeline
            cls._pipeline = hf_pipeline("token-classification", model=str(path), tokenizer=str(path),
                                        aggregation_strategy="simple", device=-1)
            logger.info("Rizzo-PII model loaded from %s (revision %s)", model_dir, found)
        except Exception as exc:  # noqa: BLE001 - a broken optional layer must not stop the engine
            logger.error("Rizzo-PII model unavailable: %s", exc)

    def detect(self, text: str, language: str = "it", layer_config: dict | None = None) -> list[PiiEntity]:
        cfg = layer_config or {}
        if self._pipeline is None or not text.strip():
            return []
        min_score = cfg.get("min_score", _MIN_SCORE)
        enabled = set(cfg["enabled_types"]) if "enabled_types" in cfg else None
        parts = chunks(text)
        try:
            results = self._pipeline([c for c, _ in parts])
        except Exception as exc:  # noqa: BLE001 - contract: never raise
            logger.error("Rizzo-PII inference failed: %s", exc)
            return []
        if parts and isinstance(results, list) and results and isinstance(results[0], dict):
            results = [results]
        spans = []
        for (_, off), res in zip(parts, results):
            for item in res:
                typ = LABEL_MAP.get(str(item.get("entity_group", "")))
                score = float(item["score"])
                if typ is None or score < min_score or (enabled is not None and typ not in enabled):
                    continue
                s, e = _widen(text, int(item["start"]) + off, int(item["end"]) + off)
                if e > s:
                    spans.append((s, e, typ, score))
        return [PiiEntity(start=s, end=e, pii_type=t, text=text[s:e], score=sc, source=LAYER)
                for s, e, t, sc in _fuse(text, spans)
                if not (t == "ADDRESS" and _LONE_ADDRESS_PART.fullmatch(text[s:e]))]
