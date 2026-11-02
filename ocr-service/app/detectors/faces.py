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
from app.imageops import Transform

_SIDE = 640  # fixed model input
_STRIDES = (8, 16, 32)
_TILE_STRIDE = 512  # 128 px overlap: a face cut by one tile is whole in the next
_MAX_TILED_SIDE = 2560  # tiles run at most at this resolution (bounds cost: <= 25 tiles)
_MIN_TILED_SIDE = 1280  # images above 640 px are tiled at >= this (2x for small faces in mid-size photos)
_ANGLES = (30.0, -30.0)  # extra whole-image passes for tilted heads (YuNet is trained mostly upright)
_GROW_X, _GROW_Y = 0.15, 0.2  # hair, ears, chin


class YuNet:
    """Why: faces are biometric PII (GDPR art. 9); photos of IDs, badges and people must hide them.
    What: ``detect(image)`` -> face Hits in image pixels: one whole-image pass (letterboxed to
    640), two more with the image turned by +/-30 deg (tilted heads; boxes map back as the
    envelope of the turned box) plus, above 640 px, overlapping 640 px tiles at 1280-2560 px
    (small faces in group photos and mid-size images). Boxes are grown to cover hair/ears.
    Low score (< ``review_score``), small (< ``review_side`` px) or profile faces (nose far off
    the eye midline) are flagged ``needs_review``.
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

    def _letterbox(self, image: Image.Image) -> tuple[Image.Image, float]:
        scale = _SIDE / max(image.size)
        canvas = Image.new("RGB", (_SIDE, _SIDE))
        canvas.paste(image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                  Image.Resampling.BILINEAR))
        return canvas, scale

    def _turned(self, image: Image.Image, angle: float) -> list[Hit]:
        """One pass on the image turned CCW by ``angle``; boxes mapped back (envelope, image pixels)."""
        small, factor = image, 1.0
        if max(image.size) > _SIDE:
            factor = _SIDE / max(image.size)
            small = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))),
                                 Image.Resampling.BILINEAR)
        turned = small.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=(0, 0, 0))
        canvas, scale = self._letterbox(turned)
        back = Transform(angle, (turned.width / 2, turned.height / 2), (small.width / 2, small.height / 2),
                         1 / factor, image.width, image.height)
        return [Hit(h.type, tuple(float(c) for c in back.box(h.bbox)), h.score, h.needs_review)  # type: ignore[arg-type]
                for h in self._decode(self._run(canvas), scale, 0.0, 0.0)]

    def detect(self, image: Image.Image) -> list[Hit]:
        """Why/What: see class. Test: a white page returns []."""
        image = image.convert("RGB")
        width, height = image.size
        canvas, scale = self._letterbox(image)
        hits = self._decode(self._run(canvas), scale, 0.0, 0.0)
        for angle in _ANGLES:
            hits += self._turned(image, angle)
        if max(width, height) > _SIDE:
            tile_scale = min(_MAX_TILED_SIDE, max(_MIN_TILED_SIDE, max(width, height))) / max(width, height)
            work = image
            if tile_scale != 1.0:
                work = image.resize((round(width * tile_scale), round(height * tile_scale)), Image.Resampling.BILINEAR)
            for top in _starts(work.height):
                for left in _starts(work.width):
                    tile = Image.new("RGB", (_SIDE, _SIDE))
                    tile.paste(work.crop((left, top, min(work.width, left + _SIDE), min(work.height, top + _SIDE))))
                    hits += self._decode(self._run(tile), tile_scale, left / tile_scale, top / tile_scale)
        return [Hit(h.type, grow(h.bbox, _GROW_X, _GROW_Y, width, height), h.score, h.needs_review) for h in _merge(nms(hits))]


def _merge(hits: list[Hit], share: float = 0.5) -> list[Hit]:
    """Why: a turned pass reports the same face as a larger envelope that IoU-NMS keeps (one box
    mostly inside the other). What: boxes whose intersection covers >= ``share`` of the smaller
    one become their union (over-covers, never under-covers), keeping the best score/review flag.
    Test: (0,0,10,10) 0.9 and (2,2,20,20) 0.6 -> one hit (0,0,20,20) score 0.9.
    """
    out: list[Hit] = []
    for hit in hits:  # nms() output: best score first
        for i, kept in enumerate(out):
            a, b = kept.bbox, hit.bbox
            w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if w > 0 and h > 0 and w * h >= share * smaller:
                out[i] = Hit(kept.type, (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])),
                             kept.score, kept.needs_review)
                break
        else:
            out.append(hit)
    return out


def _starts(length: int) -> list[int]:
    """Tile origins covering ``length`` with 640 px tiles every 512 px (last tile flush with the end)."""
    if length <= _SIDE:
        return [0]
    starts = list(range(0, length - _SIDE, _TILE_STRIDE))
    return [*starts, length - _SIDE]
