"""Face detection with YuNet (OpenCV Zoo face_detection_yunet_2023mar, MIT) on onnxruntime.

OpenCV itself is not used (its wheels bundle LGPL FFmpeg): the model's pre/post-processing is
re-implemented from the published model card: BGR float input 640x640 (no normalisation),
per-stride (8/16/32) cls/obj/bbox/kps heads, score = sqrt(cls * obj), box centre = (cell +
offset) * stride, size = exp(log-size) * stride.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.detectors import Hit, grow, nms

_SIDE = 640  # fixed model input
_STRIDES = (8, 16, 32)
_TILE_STRIDE = 512  # 128 px overlap: a face cut by one tile is whole in the next
_MAX_TILED_SIDE = 2560  # tiles run at most at this resolution (bounds cost: <= 25 tiles)
_GROW_X, _GROW_Y = 0.15, 0.2  # hair, ears, chin


class YuNet:
    """Why: faces are biometric PII (GDPR art. 9); photos of IDs, badges and people must hide them.
    What: ``detect(image)`` -> face Hits in image pixels: one whole-image pass (letterboxed to
    640) plus, for large images, overlapping 640 px tiles at up to 2560 px (small faces in group
    photos). Boxes are grown to cover hair/ears. Low score, small (< ``review_side`` px) or
    profile faces (nose far off the eye midline) are flagged ``needs_review``.
    Test: the public-domain Mona Lisa fixture yields one FACE around (116, 75, 197, 178).
    """

    def __init__(self, model_path: Path, threshold: float = 0.6, review_score: float = 0.8,
                 review_side: int = 32) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self._outputs = [o.name for o in self._session.get_outputs()]
        self._threshold, self._review_score, self._review_side = threshold, review_score, review_side

    def ready(self) -> dict[str, object]:
        """Why: readiness reports the model. What: ok + model name. Test: ok is True once loaded."""
        return {"ok": True, "model": "yunet-2023mar"}

    def _run(self, canvas: Image.Image) -> dict[str, np.ndarray]:
        x = np.asarray(canvas.convert("RGB"), dtype=np.float32)[:, :, ::-1].transpose(2, 0, 1)[None]
        return dict(zip(self._outputs, self._session.run(None, {"input": np.ascontiguousarray(x)})))

    def _decode(self, out: dict[str, np.ndarray], scale: float, ox: float, oy: float) -> list[Hit]:
        """Model-grid outputs -> Hits in source pixels (``source = canvas / scale + offset``)."""
        hits: list[Hit] = []
        for stride in _STRIDES:
            cols = _SIDE // stride
            score = np.sqrt(np.clip(out[f"cls_{stride}"][0, :, 0], 0, 1) * np.clip(out[f"obj_{stride}"][0, :, 0], 0, 1))
            for i in np.nonzero(score >= self._threshold)[0].tolist():
                row, col = divmod(i, cols)
                bx = out[f"bbox_{stride}"][0, i]
                kps = out[f"kps_{stride}"][0, i]
                cx, cy = (col + bx[0]) * stride, (row + bx[1]) * stride
                w, h = math.exp(bx[2]) * stride, math.exp(bx[3]) * stride
                box = (ox + (cx - w / 2) / scale, oy + (cy - h / 2) / scale,
                       ox + (cx + w / 2) / scale, oy + (cy + h / 2) / scale)
                # landmarks: right eye, left eye, nose (cell offsets * stride, like the box centre)
                eye_r, eye_l, nose = ((col + kps[2 * k]) * stride for k in range(3))
                eye_gap = abs(eye_l - eye_r)
                profile = eye_gap < 1e-3 or abs(nose - (eye_r + eye_l) / 2) > 0.45 * eye_gap
                small = min(w, h) / scale < self._review_side
                hits.append(Hit("FACE", box, float(score[i]),
                                bool(score[i] < self._review_score or small or profile)))
        return hits

    def detect(self, image: Image.Image) -> list[Hit]:
        """Why/What: see class. Test: a white page returns []."""
        width, height = image.size
        scale = _SIDE / max(width, height)
        canvas = Image.new("RGB", (_SIDE, _SIDE))
        canvas.paste(image.convert("RGB").resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                                 Image.Resampling.BILINEAR))
        hits = self._decode(self._run(canvas), scale, 0.0, 0.0)
        if max(width, height) > _SIDE * 1.5:
            tile_scale = min(1.0, _MAX_TILED_SIDE / max(width, height))
            work = image.convert("RGB")
            if tile_scale < 1.0:
                work = work.resize((round(width * tile_scale), round(height * tile_scale)), Image.Resampling.BILINEAR)
            for top in _starts(work.height):
                for left in _starts(work.width):
                    tile = Image.new("RGB", (_SIDE, _SIDE))
                    tile.paste(work.crop((left, top, min(work.width, left + _SIDE), min(work.height, top + _SIDE))))
                    hits += self._decode(self._run(tile), tile_scale, left / tile_scale, top / tile_scale)
        return [Hit(h.type, grow(h.bbox, _GROW_X, _GROW_Y, width, height), h.score, h.needs_review) for h in nms(hits)]


def _starts(length: int) -> list[int]:
    """Tile origins covering ``length`` with 640 px tiles every 512 px (last tile flush with the end)."""
    if length <= _SIDE:
        return [0]
    starts = list(range(0, length - _SIDE, _TILE_STRIDE))
    return [*starts, length - _SIDE]
