"""Handwritten signatures and stamps on an OCR'd page (heuristic; numpy + Pillow only).

No model: no permissively licensed signature/stamp detector with clear weight licences was
found (the public ones are YOLO/Ultralytics, AGPL, or have no stated weight licence), so this
is a classifier over the same ink mask that ``ink_without_text`` uses, plus the OCR words of
the same page (labels such as "Firma" / "Timbro", and the text to ignore) and its colours.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from app.detectors import Hit, grow, iou
from app.imageops import _sweep, components, ink_probe

MARKS = ("signature", "stamp")
# Label words only (not "sottoscritto"/"titolare": they are common in body text next to logos).
SIGNATURE_LABEL = re.compile(r"^(firm[aeo]|firmat[oa]|f\.to|signature|signed|dichiarante|fede)\b", re.IGNORECASE)
STAMP_LABEL = re.compile(r"^(timbr[oi]|sigill[oi]|stamp|seal)\b", re.IGNORECASE)
_LABEL_DX_MM, _LABEL_DY_MM = 110.0, 35.0  # a label annotates ink up to this far (right of / below / above it)
_SIG_GROW, _STAMP_GROW, _GROW_MM = (0.15, 0.3), (0.08, 0.08), 2.0  # generous: strokes fade at the edges
_MAX_SHARE = 0.25  # a mark never covers more than a quarter of the page


@dataclass(frozen=True)
class MarkWord:
    """Why: the classifier needs OCR text (labels) and where confident text is (not a mark).
    What: text, confidence 0-100 and box in the pixels of the analysed image.
    Test: ``MarkWord("Firma", 90, (0, 0, 10, 5)).text == "Firma"``.
    """

    text: str
    conf: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class Shape:
    """Why: one place for the measurements every rule reads (and tests/benchmarks print).
    What: size in mm, ink density, stroke width (mm), share of ink in the largest stroke,
    gradient-orientation entropy (0 = one direction, 1 = all directions) and ring/frame scores.
    Test: a drawn circle has ``ring >= 0.8``; a straight bar has ``entropy < 0.5``.
    """

    w_mm: float
    h_mm: float
    density: float
    stroke_mm: float
    largest: float
    entropy: float
    ring: float
    inner: float
    frame: float


def _odd(value: float) -> int:
    return max(3, int(round(value)) | 1)


def _dilate(mask: np.ndarray, size: int) -> np.ndarray:
    grown = _sweep(_sweep(mask.astype(np.uint8), size, 0, np.max), size, 1, np.max)
    return grown.astype(bool)


def _entropy(mask: np.ndarray) -> float:
    """Gradient-orientation entropy of a binary stroke image (8 bins over 0..pi, magnitude-weighted)."""
    if mask.shape[0] < 5 or mask.shape[1] < 5:
        return 0.0
    # smoothed first: on a raw binary mask central differences only see 4 directions in 0..pi
    a = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.BoxBlur(1)), dtype=np.float32)
    gx = a[1:-1, 2:] - a[1:-1, :-2]
    gy = a[2:, 1:-1] - a[:-2, 1:-1]
    mag = np.hypot(gx, gy)
    if float(mag.sum()) <= 0:
        return 0.0
    angle = np.mod(np.arctan2(gy, gx), math.pi)
    hist, _ = np.histogram(angle, bins=8, range=(0, math.pi), weights=mag)
    p = hist[hist > 0] / hist.sum()
    return float(-(p * np.log(p)).sum() / math.log(8))


def _ring(mask: np.ndarray) -> tuple[float, float]:
    """(angular coverage of the outer ellipse band, ink density inside r < 0.6) for a round stamp."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return 0.0, 1.0
    nx, ny = (xs - (w - 1) / 2) / (w / 2), (ys - (h - 1) / 2) / (h / 2)
    r = np.hypot(nx, ny)
    band = (r >= 0.78) & (r <= 1.1)
    sectors = np.unique((np.arctan2(ny[band], nx[band]) / (2 * math.pi) * 36).astype(int) % 36)
    inner_area = math.pi * 0.36 * (w / 2) * (h / 2)
    return len(sectors) / 36, float(np.count_nonzero(r < 0.6)) / max(1.0, inner_area)


def _frame(mask: np.ndarray) -> float:
    """Smallest share, over the 4 sides, of positions with ink in that side's border band."""
    h, w = mask.shape
    bx, by = max(2, round(w * 0.08)), max(2, round(h * 0.08))
    sides = (mask[:by].any(axis=0), mask[-by:].any(axis=0), mask[:, :bx].any(axis=1), mask[:, -bx:].any(axis=1))
    return float(min(side.mean() for side in sides))


def measure(mask: np.ndarray, full: np.ndarray, mm: float) -> Shape:
    """Why/What: features of one candidate. ``mask`` = its strokes (confident text removed),
    ``full`` = all its ink (for ring/frame tests: stamp text may have been read by the OCR).
    Test: see Shape.
    """
    h, w = mask.shape
    n = int(np.count_nonzero(mask))
    eroded = mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
    perimeter = max(1, n - int(np.count_nonzero(eroded)))
    sizes = [pixels for _, pixels in components(mask)] or [0]
    coverage, inner = _ring(full)
    return Shape(w_mm=w / mm, h_mm=h / mm, density=n / max(1, w * h), stroke_mm=2.0 * n / perimeter / mm,
                 largest=max(sizes) / max(1, n), entropy=_entropy(mask), ring=coverage, inner=inner,
                 frame=_frame(full))


def _near(box: Sequence[float], labels: Iterable[MarkWord], mm: float) -> bool:
    for label in labels:
        lx0, ly0, lx1, ly1 = label.bbox
        dx = max(0.0, lx0 - box[2], box[0] - lx1)
        dy = max(0.0, ly0 - box[3], box[1] - ly1)
        if dx <= _LABEL_DX_MM * mm and dy <= _LABEL_DY_MM * mm and box[2] >= lx0 - 20 * mm:
            return True
    return False


def is_round_stamp(s: Shape) -> bool:
    """Why: B/W and coloured round/oval stamps share the ring test. What: 12-70 mm, aspect
    0.5-2, outer band covered on >= 80% of the angles, sparse inside. Test: see test_marks."""
    return (12 <= s.w_mm <= 70 and 12 <= s.h_mm <= 70 and 0.5 <= s.w_mm / s.h_mm <= 2.0
            and s.ring >= 0.8 and s.inner <= 0.35)


def signature_score(s: Shape, labelled: bool) -> float:
    """Why: handwriting is curvy, connected, thin, sparse and wide; printed text the OCR missed
    is many small separate glyphs; logos are dense; rules/table residue run in one direction.
    What: 0 unless the size/density/stroke ranges hold and the strokes are curvy (orientation
    entropy >= 0.75); unlabelled ink must also be connected (largest stroke >= 25% of the ink),
    >= 20 mm wide and >= 1.5:1. Score 0.6 + 0.15 (connected) + 0.25 (near a label).
    Test: a Bezier signature next to "Firma" scores 1.0; a filled logo or a table grid scores 0.
    """
    if not (3 <= s.h_mm <= 60 and 8 <= s.w_mm <= 180 and 0.7 <= s.w_mm / s.h_mm <= 15
            and 0.03 <= s.density <= 0.4 and 0.08 <= s.stroke_mm <= 2.5 and s.entropy >= 0.75):
        return 0.0
    connected = s.largest >= 0.25
    if not labelled and (not connected or s.w_mm < 20 or s.w_mm / s.h_mm < 1.5):
        return 0.0
    return 0.6 + 0.15 * connected + 0.25 * labelled


def find_marks(rgb: Image.Image, gray: Image.Image, words: Sequence[MarkWord], dpi: int, low_conf: float,
               wanted: Sequence[str] = MARKS) -> list[Hit]:
    """Why: signatures and stamps identify people and offices; OCR cannot read them, so they
    must be found as pixels and always painted (padded generously).
    What: SIGNATURE = ink left after removing confident OCR words, merged into stroke groups,
    shaped like handwriting (score >= 0.6; confident when also near a label such as "Firma",
    otherwise needs_review). STAMP = a coloured (red/blue/violet) or B/W ink group with a ring
    (round/oval) or a coloured axis-aligned rectangular frame (confident), or a compact (<= 2.5:1)
    sparse coloured group that is not printed text or sits near "Timbro" (needs_review: tilted
    rectangular stamps, faded ones). Wide blue-pen signatures stay SIGNATURE only. Boxes in ``gray`` pixels.
    Test: test_marks.py (synthetic signatures/stamps found and painted, no hit on text/tables/logos).
    """
    ink, factor = ink_probe(gray)
    if not ink.any():
        return []
    height, width = ink.shape
    mm = max(0.5, dpi / 25.4 / factor)  # probe pixels per millimetre
    probe = [MarkWord(w.text, w.conf, tuple(c / factor for c in w.bbox)) for w in words]  # type: ignore[misc]
    sig_labels = [w for w in probe if SIGNATURE_LABEL.match(w.text.strip(":;.,()[]"))]
    stamp_labels = [w for w in probe if STAMP_LABEL.match(w.text.strip(":;.,()[]"))]
    text = np.zeros_like(ink)
    for word in probe:
        if word.conf >= low_conf:
            x0, y0, x1, y1 = word.bbox
            text[max(0, int(y0) - 1): math.ceil(y1) + 1, max(0, int(x0) - 1): math.ceil(x1) + 1] = True
    strokes = ink & ~text
    found: list[Hit] = []
    for (x0, y0, x1, y1), _ in components(_dilate(strokes, _odd(2.5 * mm))):
        if max(x1 - x0, y1 - y0) < 6 * mm:
            continue
        box = (x0, y0, x1, y1)
        shape = measure(strokes[y0:y1, x0:x1], ink[y0:y1, x0:x1], mm)
        if "stamp" in wanted and is_round_stamp(shape):
            found.append(Hit("STAMP", box, 0.9, False))
        elif "signature" in wanted:
            labelled = _near(box, sig_labels, mm)
            score = signature_score(shape, labelled)
            if score >= 0.6:
                found.append(Hit("SIGNATURE", box, score, score < 1.0))  # confident: labelled + connected
    if "stamp" in wanted and rgb.mode == "RGB":
        hsv = np.asarray(rgb.resize((width, height), Image.Resampling.BOX).convert("HSV"))
        hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        colour = (sat >= 80) & (val >= 50) & (val <= 250) & ((hue <= 14) | (hue >= 135))  # red, blue, violet
        for (x0, y0, x1, y1), _ in components(_dilate(colour, _odd(1.5 * mm))):
            w_mm, h_mm = (x1 - x0) / mm, (y1 - y0) / mm
            if not (10 <= w_mm <= 90 and 8 <= h_mm <= 90 and 0.4 <= w_mm / h_mm <= 3.0):
                continue
            box = (x0, y0, x1, y1)
            if any(h.type == "STAMP" and iou(h.bbox, box) > 0.3 for h in found):
                continue
            region = colour[y0:y1, x0:x1]
            shape = measure(region, region, mm)
            printed = float(np.count_nonzero(region & text[y0:y1, x0:x1])) / max(1, int(np.count_nonzero(region)))
            framed = shape.frame >= 0.8 and shape.inner <= 0.5
            # Hits are only ever added, never replaced: a signature across a stamp keeps both boxes.
            if is_round_stamp(shape) or framed:
                found.append(Hit("STAMP", box, 0.9, False))
            elif shape.inner <= 0.5 and 0.5 <= w_mm / h_mm <= 2.5 and (_near(box, stamp_labels, mm) or (
                    printed < 0.5 and 0.03 <= shape.density <= 0.4)):  # filled logos are dense inside
                found.append(Hit("STAMP", box, 0.6, True))  # e.g. a tilted rectangular stamp
    return _finish(found, factor, mm, gray.width, gray.height)


def _finish(found: list[Hit], factor: float, mm: float, width: int, height: int) -> list[Hit]:
    """Probe boxes -> grown, clamped boxes in ``gray`` pixels; drops anything page-sized."""
    out: list[Hit] = []
    pad = _GROW_MM * mm * factor
    for hit in found:
        fx, fy = _SIG_GROW if hit.type == "SIGNATURE" else _STAMP_GROW
        x0, y0, x1, y1 = grow(tuple(c * factor for c in hit.bbox), fx, fy, width, height)  # type: ignore[arg-type]
        box = (max(0.0, x0 - pad), max(0.0, y0 - pad), min(float(width), x1 + pad), min(float(height), y1 + pad))
        if (box[2] - box[0]) * (box[3] - box[1]) <= _MAX_SHARE * width * height:
            out.append(Hit(hit.type, box, hit.score, hit.needs_review))
    return out
