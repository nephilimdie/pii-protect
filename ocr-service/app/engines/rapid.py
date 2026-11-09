"""PP-OCRv4 mobile (RapidOCR-packaged ONNX models) runner on onnxruntime + numpy + Pillow.

The ``rapidocr_onnxruntime`` package itself is NOT a runtime dependency: it hard-requires
opencv-python, whose wheels bundle LGPL FFmpeg/Qt. We only take its Apache-2.0 model files
(see scripts/fetch_models.sh) and re-implement the small pre/post-processing it does:
DB text detection (threshold -> components -> unclip) and CTC greedy decoding.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.engines import RawWord, remaining
from app.imageops import components

_DET_THRESH = 0.3
_BOX_THRESH = 0.5
_UNCLIP_RATIO = 1.6
_REC_HEIGHT = 48
_REC_MAX_WIDTH = 3200
_MIN_BOX_SIDE = 4


def _normalize(rgb: np.ndarray) -> np.ndarray:
    """Why: PP-OCR models expect (x/255 - 0.5) / 0.5 in NCHW. What: HWC uint8 -> 1CHW float32. Test: 255 -> 1.0."""
    return ((rgb.astype(np.float32) / 127.5) - 1.0).transpose(2, 0, 1)[None]


class RapidOcr:
    """Why: photos/screenshots (coloured backgrounds, UI text, low DPI) are where Tesseract's
    layout analysis fails; a learned detector finds text regions Tesseract misses.
    What: detects text lines, recognises each line, splits into words with per-character x
    positions derived from CTC time steps. One intra-op thread per call (pool sizes workers).
    Test: ``RapidOcr(model_dir).recognize(img_with_text, "ita", 300, deadline)`` returns words.
    """

    name = "rapidocr"

    def __init__(self, model_dir: Path, max_side: int = 2000, rec_threads: int = 1) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self._det = ort.InferenceSession(str(model_dir / "det.onnx"), options, providers=providers)
        self._rec = ort.InferenceSession(str(model_dir / "rec.onnx"), options, providers=providers)
        characters = self._rec.get_modelmeta().custom_metadata_map["character"].splitlines()
        self._alphabet = ["", *characters, " "]  # CTC blank first, space last (PP-OCR convention)
        self._max_side = max_side
        self._model_dir = model_dir
        # one pool per process: concurrent requests share it, so threads never exceed rec_threads
        self._pool = ThreadPoolExecutor(rec_threads, thread_name_prefix="ocr-rec") if rec_threads > 1 else None

    def ready(self) -> dict[str, object]:
        """Why: readiness reports model presence. What: ok + alphabet size. Test: alphabet == 6625."""
        return {"ok": len(self._alphabet) > 2, "alphabet": len(self._alphabet), "models": "PP-OCRv4-mobile"}

    def detect(self, gray: Image.Image) -> list[tuple[float, float, float, float]]:
        """Why: line boxes drive recognition. What: DB detection on a <=max_side copy; returns
        unclipped axis-aligned line boxes in ``gray`` pixels.
        Test: a white image returns []; one text line returns one box covering it.
        """
        factor = min(1.0, self._max_side / max(gray.size))
        width = max(32, int(round(gray.width * factor / 32)) * 32)
        height = max(32, int(round(gray.height * factor / 32)) * 32)
        resized = gray.convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
        prob = self._det.run(None, {"x": _normalize(np.asarray(resized))})[0][0, 0]
        mask = prob > _DET_THRESH
        mask[:-1] |= mask[1:]  # 2x2 dilation, as in PP-OCR post-processing
        mask[:, :-1] |= mask[:, 1:]
        sx, sy = gray.width / width, gray.height / height
        boxes: list[tuple[float, float, float, float]] = []
        for (x0, y0, x1, y1), _ in components(mask):
            w, h = x1 - x0, y1 - y0
            if min(w, h) < 2 or float(prob[y0:y1, x0:x1].mean()) < _BOX_THRESH:
                continue
            offset = (w * h * _UNCLIP_RATIO) / (2 * (w + h))
            box = (max(0.0, (x0 - offset) * sx), max(0.0, (y0 - offset) * sy),
                   min(gray.width, (x1 + offset) * sx), min(gray.height, (y1 + offset) * sy))
            if min(box[2] - box[0], box[3] - box[1]) >= _MIN_BOX_SIDE:
                boxes.append(box)
        return sorted(boxes, key=lambda b: (round(b[1] / 10), b[0]))

    def _read_line(self, gray: Image.Image, box: tuple[float, float, float, float]) -> list[tuple[str, float, float, float]]:
        """Why: word boxes need character positions. What: returns ``(char, prob, x0, x1)`` in
        ``gray`` pixels for each decoded character (CTC greedy, repeats/blanks collapsed).
        Test: a crop containing "AB" decodes to two characters with increasing x.
        """
        x0, y0, x1, y1 = box
        crop = gray.crop((int(x0), int(y0), math.ceil(x1), math.ceil(y1))).convert("RGB")
        target = min(_REC_MAX_WIDTH, max(16, round(crop.width * _REC_HEIGHT / max(1, crop.height))))
        resized = crop.resize((target, _REC_HEIGHT), Image.Resampling.BILINEAR)
        probs = self._rec.run(None, {"x": _normalize(np.asarray(resized))})[0][0]
        best, score = probs.argmax(axis=1), probs.max(axis=1)
        step = crop.width / len(best)
        chars: list[tuple[str, float, float, float]] = []
        previous = 0
        for t, (index, prob) in enumerate(zip(best.tolist(), score.tolist())):
            if index != 0 and index != previous and index < len(self._alphabet):
                chars.append((self._alphabet[index], prob, x0 + t * step, x0 + (t + 1) * step))
            elif index == previous and index != 0 and chars:
                char, p, start, _ = chars[-1]
                chars[-1] = (char, max(p, prob), start, x0 + (t + 1) * step)
            previous = index
        return chars

    def recognize(self, gray: Image.Image, lang: str, dpi: int, deadline: float) -> list[RawWord]:
        """Why/What: see class; ``lang``/``dpi`` are accepted for interface parity (the model is
        multilingual and resolution-normalised). Test: deadline in the past raises 504.
        """
        remaining(deadline)
        boxes = self.detect(gray)

        def read(box: tuple[float, float, float, float]) -> list[tuple[str, float, float, float]]:
            remaining(deadline)
            return self._read_line(gray, box)

        # ORT run() is thread-safe; map keeps line order, so the words are identical to a sequential read
        lines = list(self._pool.map(read, boxes)) if self._pool and len(boxes) > 1 else [read(b) for b in boxes]
        words: list[RawWord] = []
        for line_id, (box, chars) in enumerate(zip(boxes, lines)):
            current: list[tuple[str, float, float, float]] = []
            for item in [*chars, (" ", 1.0, box[2], box[2])]:
                if item[0] != " ":
                    current.append(item)
                    continue
                if current:
                    text = "".join(c[0] for c in current)
                    conf = 100.0 * float(min(c[1] for c in current))  # weakest character: fail-closed
                    pad = (current[0][3] - current[0][2]) * 0.5
                    bbox = (max(box[0], current[0][2] - pad), box[1], min(box[2], current[-1][3] + pad), box[3])
                    words.append(RawWord(text, conf, bbox, line_id, line_id))
                current = []
        return words
