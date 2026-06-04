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
    "private_url":     "SECRET",
    "account_number":  "SECRET",
    "secret":          "SECRET",
}

_MIN_SCORE = 0.70


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

    def detect(self, text: str) -> list[PiiEntity]:
        if not self.is_available():
            return []
        try:
            return self._run(text)
        except Exception as exc:
            logger.warning("PrivacyFilter inference error: %s", exc)
            return []

    def _run(self, text: str) -> list[PiiEntity]:
        entities: list[PiiEntity] = []
        cursor = 0
        for line in text.splitlines(keepends=True):
            line_stripped = line.rstrip("\n\r")
            if line_stripped.strip():
                for e in self._run_line(line_stripped, cursor):
                    entities.append(e)
            cursor += len(line)
        return entities

    def _run_line(self, line: str, global_offset: int) -> list[PiiEntity]:
        import numpy as np

        enc = self._tokenizer.encode(line, add_special_tokens=False)
        input_ids = enc.ids[:512]
        if not input_ids:
            return []
        attention_mask = [1] * len(input_ids)
        offset_mapping = [list(o) for o in enc.offsets[:512]]

        inputs = {
            "input_ids": np.array([input_ids], dtype=np.int64),
            "attention_mask": np.array([attention_mask], dtype=np.int64),
        }
        input_names = {inp.name for inp in self._session.get_inputs()}
        inputs = {k: v for k, v in inputs.items() if k in input_names}

        logits = self._session.run(None, inputs)[0][0]
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
            if avg_score < _MIN_SCORE:
                continue
            pii_type = _LABEL_MAP.get(span["group"])
            if pii_type is None:
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
