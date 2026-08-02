from __future__ import annotations
import logging
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "openai/privacy-filter"
_ONNX_FILE = "onnx/model_quantized.onnx"

# id → entity_group (from config.json id2label, BIOES prefix stripped)
_ID2LABEL: dict[int, str] = {
    0:  "O",
    1:  "account_number", 2:  "account_number", 3:  "account_number", 4:  "account_number",
    5:  "private_address", 6:  "private_address", 7:  "private_address", 8:  "private_address",
    9:  "private_date",   10: "private_date",   11: "private_date",   12: "private_date",
    13: "private_email",  14: "private_email",  15: "private_email",  16: "private_email",
    17: "private_person", 18: "private_person", 19: "private_person", 20: "private_person",
    21: "private_phone",  22: "private_phone",  23: "private_phone",  24: "private_phone",
    25: "private_url",    26: "private_url",    27: "private_url",    28: "private_url",
    29: "secret",         30: "secret",         31: "secret",         32: "secret",
}

# BIOES prefix id (within each group: B=0, I=1, E=2, S=3 → indices offset by 4*group)
_BIOES_PREFIX: dict[int, str] = {}
for _gid, (_start, _label) in enumerate([
    (1, "account_number"), (5, "private_address"), (9, "private_date"),
    (13, "private_email"), (17, "private_person"), (21, "private_phone"),
    (25, "private_url"), (29, "secret"),
]):
    _BIOES_PREFIX[_start]     = "B"
    _BIOES_PREFIX[_start + 1] = "I"
    _BIOES_PREFIX[_start + 2] = "E"
    _BIOES_PREFIX[_start + 3] = "S"

_LABEL_MAP: dict[str, str | None] = {
    "private_person":  "PERSON",
    "private_email":   "EMAIL",
    "private_phone":   "PHONE",
    "private_address": "ADDRESS",
    "private_date":    "DATE",
    "private_url":     "URL",
    "account_number":  "ACCOUNT_NUMBER",
    "secret":          "SECRET",
}

_MIN_SCORE = 0.70
_MAX_TOKENS = 512
_LINE_BATCH_SIZE = 16

PreparedLine = tuple[str, int, list[int], list[tuple[int, int]]]


def _bioes_to_spans(label_ids: list[int], scores: list[float], offsets: list[tuple[int, int]]) -> list[dict]:
    """Collapse BIOES token labels into entity spans with char offsets."""
    spans = []
    current: dict | None = None

    for i, lid in enumerate(label_ids):
        if lid == 0:
            if current:
                spans.append(current)
                current = None
            continue

        group = _ID2LABEL.get(lid, "O")
        prefix = _BIOES_PREFIX.get(lid, "O")
        score = scores[i]
        char_start, char_end = offsets[i]

        if prefix in ("B", "S"):
            if current:
                spans.append(current)
            current = {
                "group": group,
                "start": char_start,
                "end": char_end,
                "scores": [score],
            }
            if prefix == "S":
                spans.append(current)
                current = None

        elif prefix in ("I", "E") and current and current["group"] == group:
            current["end"] = char_end
            current["scores"].append(score)
            if prefix == "E":
                spans.append(current)
                current = None
        else:
            if current:
                spans.append(current)
            current = None

    if current:
        spans.append(current)

    return spans


class PrivacyFilterDetector(DetectorContract):
    _session = None
    _tokenizer = None

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    @property
    def layer_name(self) -> str:
        return "privacy_filter"

    @property
    def priority(self) -> int:
        return 20

    def is_available(self) -> bool:
        return self._session is not None and self._tokenizer is not None

    @classmethod
    def preload(cls, model: str = _DEFAULT_MODEL) -> None:
        try:
            import os
            import onnxruntime as ort
            from tokenizers import Tokenizer
            from huggingface_hub import snapshot_download

            model_dir = snapshot_download(
                repo_id=model,
                allow_patterns=["onnx/model_quantized.onnx*", "tokenizer.json"],
            )
            onnx_path = os.path.join(model_dir, _ONNX_FILE)
            cls._session = ort.InferenceSession(
                onnx_path,
                providers=["CPUExecutionProvider"],
            )
            tok_path = os.path.join(model_dir, "tokenizer.json")
            cls._tokenizer = Tokenizer.from_file(tok_path)
            logger.info("PrivacyFilter model loaded via ONNX: %s", model)
        except Exception as exc:
            logger.warning("PrivacyFilter model unavailable: %s", exc)

    def detect(self, text: str, language: str = "it", layer_config: dict | None = None) -> list[PiiEntity]:
        cfg = layer_config or {}
        min_score = cfg.get("min_score", _MIN_SCORE)
        min_chars = cfg.get("min_chars", None)
        enabled_types: set[str] | None = (
            set(cfg["enabled_types"]) if "enabled_types" in cfg else None
        )
        if not self.is_available():
            return []
        if min_chars is not None and len(text) < min_chars:
            return []
        try:
            return self._run(text, min_score=min_score, enabled_types=enabled_types)
        except Exception as exc:
            logger.warning("PrivacyFilter inference error: %s", exc)
            return []

    def _run(self, text: str, min_score: float = _MIN_SCORE, enabled_types: set[str] | None = None) -> list[PiiEntity]:
        prepared: list[PreparedLine] = []
        cursor = 0
        for line in text.splitlines(keepends=True):
            line_stripped = line.rstrip("\n\r")
            if line_stripped.strip():
                item = self._prepare_line(line_stripped, cursor)
                if item is not None:
                    prepared.append(item)
            cursor += len(line)

        entities: list[PiiEntity] = []
        for start in range(0, len(prepared), _LINE_BATCH_SIZE):
            entities.extend(self._run_batch(
                prepared[start:start + _LINE_BATCH_SIZE],
                min_score,
                enabled_types,
            ))
        return entities

    def _run_line(self, line: str, global_offset: int, min_score: float = _MIN_SCORE, enabled_types: set[str] | None = None) -> list[PiiEntity]:
        prepared = self._prepare_line(line, global_offset)
        if prepared is None:
            return []
        return self._run_batch([prepared], min_score, enabled_types)

    def _prepare_line(self, line: str, global_offset: int) -> PreparedLine | None:
        enc = self._tokenizer.encode(line, add_special_tokens=False)
        input_ids = enc.ids[:_MAX_TOKENS]
        if not input_ids:
            return None
        offsets = [tuple(offset) for offset in enc.offsets[:_MAX_TOKENS]]
        return line, global_offset, input_ids, offsets

    def _run_batch(
        self,
        prepared: list[PreparedLine],
        min_score: float,
        enabled_types: set[str] | None,
    ) -> list[PiiEntity]:
        import numpy as np

        if not prepared:
            return []

        max_length = max(len(item[2]) for item in prepared)
        pad_id = self._tokenizer.token_to_id("[PAD]") or 0
        input_ids = np.full((len(prepared), max_length), pad_id, dtype=np.int64)
        attention_mask = np.zeros((len(prepared), max_length), dtype=np.int64)
        for index, (_, _, ids, _) in enumerate(prepared):
            input_ids[index, :len(ids)] = ids
            attention_mask[index, :len(ids)] = 1

        inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        input_names = {inp.name for inp in self._session.get_inputs()}
        inputs = {k: v for k, v in inputs.items() if k in input_names}

        try:
            logits_batch = self._session.run(None, inputs)[0]
        except Exception:
            if len(prepared) == 1:
                raise
            logger.warning("PrivacyFilter batch inference unavailable; falling back to single lines")
            return [
                entity
                for item in prepared
                for entity in self._run_batch([item], min_score, enabled_types)
            ]

        entities: list[PiiEntity] = []
        for index, (line, global_offset, ids, offsets) in enumerate(prepared):
            entities.extend(self._entities_from_logits(
                line,
                global_offset,
                logits_batch[index][:len(ids)],
                offsets,
                min_score,
                enabled_types,
            ))
        return entities

    def _entities_from_logits(
        self,
        line: str,
        global_offset: int,
        logits,
        offset_mapping: list[tuple[int, int]],
        min_score: float,
        enabled_types: set[str] | None,
    ) -> list[PiiEntity]:
        label_ids = logits.argmax(axis=-1).tolist()
        probs = _softmax(logits)
        scores = probs[range(len(label_ids)), label_ids].tolist()

        valid_ids, valid_scores, valid_offsets = [], [], []
        for lid, sc, off in zip(label_ids, scores, offset_mapping):
            if off[0] == off[1]:
                continue
            valid_ids.append(lid)
            valid_scores.append(sc)
            valid_offsets.append(tuple(off))

        spans = _bioes_to_spans(valid_ids, valid_scores, valid_offsets)

        entities = []
        for span in spans:
            if not span["scores"]:
                continue
            avg_score = sum(span["scores"]) / len(span["scores"])
            if avg_score < min_score:
                continue
            pii_type = _LABEL_MAP.get(span["group"])
            if pii_type is None:
                continue
            if enabled_types is not None and pii_type not in enabled_types:
                continue
            start = global_offset + span["start"]
            end = global_offset + span["end"]
            entities.append(PiiEntity(
                start=start,
                end=end,
                pii_type=pii_type,
                text=line[span["start"]:span["end"]],
                score=round(avg_score, 4),
            ))
        return entities


def _softmax(x):
    import numpy as np
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)
