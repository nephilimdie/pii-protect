"""Pure image helpers: geometry mapping, deskew, preprocessing passes, ink analysis.

Ideas (not code) borrowed from the document-intelligence ImagePreprocessor: projection-profile
deskew and contrast/binarize retry passes. Everything here is numpy + Pillow (no OpenCV).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

BBoxF = tuple[float, float, float, float]
BBox = tuple[int, int, int, int]

_SKEW_PROBE_SIDE = 900
_INK_PROBE_SIDE = 1200


@dataclass(frozen=True)
class Transform:
    """Why: OCR runs on a resized/deskewed copy, but boxes must land on the caller's page pixels.
    What: maps a point of the processed image back to the reported page frame (rotation about
    the image centres, then uniform scale), and clamps envelopes to the page.
    Test: ``Transform.identity(10, 10).box((1, 2, 3, 4)) == (1, 2, 3, 4)``.
    """

    angle: float  # degrees the processed image was rotated (Pillow, counter-clockwise)
    src_center: tuple[float, float]  # centre of the processed image
    dst_center: tuple[float, float]  # centre of the unrotated working image
    scale: float  # reported pixels per working pixel
    width: int  # reported page width
    height: int  # reported page height

    @staticmethod
    def identity(width: int, height: int, scale: float = 1.0) -> Transform:
        """Why: most pages need no rotation. What: transform with only a scale. Test: see class."""
        return Transform(0.0, (0.0, 0.0), (0.0, 0.0), scale, width, height)

    def point(self, x: float, y: float) -> tuple[float, float]:
        """Why: inverse of Pillow's CCW rotation. What: processed (x, y) -> reported (x, y).
        Test: rotating a dot image and mapping the dot's new position returns the old position.
        """
        if self.angle:
            rad = math.radians(self.angle)
            cos, sin = math.cos(rad), math.sin(rad)
            dx, dy = x - self.src_center[0], y - self.src_center[1]
            x = self.dst_center[0] + cos * dx - sin * dy
            y = self.dst_center[1] + sin * dx + cos * dy
        return x * self.scale, y * self.scale

    def box(self, bbox: BBoxF) -> BBox:
        """Why: a rotated box is not axis-aligned; redaction must over-cover, never under-cover.
        What: axis-aligned envelope of the 4 mapped corners, rounded outward, clamped to page.
        Test: identity maps (1.2, 2.7, 3.1, 4.0) to (1, 2, 4, 4).
        """
        x0, y0, x1, y1 = bbox
        corners = [self.point(x, y) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        return (
            max(0, math.floor(min(xs))),
            max(0, math.floor(min(ys))),
            min(self.width, math.ceil(max(xs))),
            min(self.height, math.ceil(max(ys))),
        )


def to_gray(image: Image.Image) -> Image.Image:
    """Why: both engines and all analysis work on luminance; alpha must become white paper.
    What: flattens transparency onto white and converts to 8-bit grayscale.
    Test: an RGBA fully transparent image becomes all-255 "L".
    """
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(canvas, rgba)
    return image.convert("L") if image.mode != "L" else image


def otsu_threshold(array: np.ndarray) -> int:
    """Why: ink/paper split without a fixed cutoff (scans vary in exposure).
    What: vectorised Otsu threshold over the 8-bit histogram.
    Test: an image of half 20s and half 230s returns a value in [20, 230).
    """
    hist = np.bincount(array.ravel(), minlength=256).astype(np.float64)
    weights = np.cumsum(hist)
    means = np.cumsum(hist * np.arange(256))
    total, total_mean = weights[-1], means[-1]
    back = weights
    fore = total - weights
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (total_mean * back - means * total) ** 2 / (back * fore)
    between[~np.isfinite(between)] = -1
    return int(np.argmax(between))


def _probe(gray: Image.Image, side: int) -> tuple[Image.Image, float]:
    """Why: analysis does not need full resolution. What: downscaled copy + factor. Test: 2400px -> 900px."""
    factor = max(gray.size) / side
    if factor <= 1:
        return gray, 1.0
    return gray.resize((round(gray.width / factor), round(gray.height / factor)), Image.Resampling.BOX), factor


def estimate_skew(gray: Image.Image, max_degrees: float) -> float:
    """Why: Tesseract line finding degrades quickly beyond ~2 degrees of skew.
    What: projection-profile search (coarse 1 deg, then fine 0.1 deg); returns the CCW angle
    that makes text lines horizontal, or 0 when the page has too little ink.
    Test: text rotated by -4 deg (CW) is estimated at +4 +/- 0.3.
    """
    if max_degrees <= 0:
        return 0.0
    small, _ = _probe(gray, _SKEW_PROBE_SIDE)
    array = np.asarray(small, dtype=np.uint8)
    ink = Image.fromarray(np.where(array < min(otsu_threshold(array), 200), 255, 0).astype(np.uint8))
    if np.count_nonzero(np.asarray(ink)) < 200:
        return 0.0

    def score(angle: float) -> float:
        profile = np.asarray(ink.rotate(angle, resample=Image.Resampling.NEAREST, fillcolor=0), dtype=np.float32).sum(axis=1)
        return float(np.var(np.diff(profile)))

    def search(center: float, span: float, step: float) -> float:
        angles = np.arange(center - span, center + span + step / 2, step)
        return float(max(angles, key=score))

    coarse = search(0.0, max_degrees, 1.0)
    return round(search(coarse, 1.0, 0.1), 2)


def rotate(gray: Image.Image, angle: float, transform: Transform) -> tuple[Image.Image, Transform]:
    """Why: deskewing must keep corners (no cropping) and remember how to map boxes back.
    What: rotates CCW with expand + white fill and returns the composed transform.
    Test: ``rotate(img, 0, t)`` returns the same image and transform.
    """
    if not angle:
        return gray, transform
    rotated = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    composed = Transform(
        angle=angle,
        src_center=(rotated.width / 2, rotated.height / 2),
        dst_center=(gray.width / 2, gray.height / 2),
        scale=transform.scale,
        width=transform.width,
        height=transform.height,
    )
    return rotated, composed


def _contrast_denoise(gray: Image.Image) -> Image.Image:
    """Why: faint scans and salt-and-pepper noise. What: autocontrast + 3x3 median. Test: output is "L"."""
    return ImageOps.autocontrast(gray, cutoff=1).filter(ImageFilter.MedianFilter(3))


def _local_binarize(gray: Image.Image) -> Image.Image:
    """Why: phone photos have uneven lighting where one global threshold drops whole areas.
    What: ink where a pixel is 12 levels darker than its ~51 px local mean (Sauvola-like).
    Test: a gradient background with dark text keeps the text and whitens the background.
    """
    array = np.asarray(gray, dtype=np.int16)
    local = np.asarray(gray.filter(ImageFilter.BoxBlur(25)), dtype=np.int16)
    return Image.fromarray(np.where(array < local - 12, 0, 255).astype(np.uint8))


def _upscale(gray: Image.Image) -> Image.Image:
    """Why: tiny text (<20 px x-height) is below Tesseract's sweet spot. What: 1.5x Lanczos. Test: size grows 1.5x."""
    return gray.resize((round(gray.width * 1.5), round(gray.height * 1.5)), Image.Resampling.LANCZOS)


# Ordered retry passes: (name, transform-of-gray, upscale factor applied to coordinates).
PASSES: tuple[tuple[str, Callable[[Image.Image], Image.Image], float], ...] = (
    ("contrast", _contrast_denoise, 1.0),
    ("local_binarize", _local_binarize, 1.0),
    ("upscale", lambda g: _upscale(_contrast_denoise(g)), 1.5),
)


def components(mask: np.ndarray) -> list[tuple[BBox, int]]:
    """Why: both RapidOCR's DB post-processing and ink analysis need connected regions, and
    OpenCV/scipy are avoided (licence/size). What: run-length union-find 8-connectivity
    labelling; returns ``((x0, y0, x1, y1), pixel_count)`` with exclusive x1/y1.
    Test: two separate 2x2 squares -> 2 components of 4 pixels each.
    """
    height = mask.shape[0]
    parent: list[int] = []
    runs: list[tuple[int, int, int]] = []  # (row, start, end) end exclusive
    prev: list[int] = []

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    padded = np.zeros((height, mask.shape[1] + 2), dtype=np.int8)
    padded[:, 1:-1] = mask.astype(bool)
    edges = np.diff(padded, axis=1)
    for row in range(height):
        starts = np.flatnonzero(edges[row] == 1)
        ends = np.flatnonzero(edges[row] == -1)
        current: list[int] = []
        pointer = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            index = len(runs)
            runs.append((row, start, end))
            parent.append(index)
            current.append(index)
            while pointer < len(prev) and runs[prev[pointer]][2] < start:
                pointer += 1
            probe = pointer
            while probe < len(prev) and runs[prev[probe]][1] <= end:
                a, b = find(index), find(prev[probe])
                if a != b:
                    parent[max(a, b)] = min(a, b)
                probe += 1
        prev = current
    boxes: dict[int, list[int]] = {}
    for index, (row, start, end) in enumerate(runs):
        root = find(index)
        box = boxes.setdefault(root, [start, row, end, row + 1, 0])
        box[0], box[1] = min(box[0], start), min(box[1], row)
        box[2], box[3] = max(box[2], end), max(box[3], row + 1)
        box[4] += end - start
    return [((b[0], b[1], b[2], b[3]), b[4]) for b in boxes.values()]


def ink_without_text(gray: Image.Image, text_boxes: Iterable[BBoxF]) -> list[BBoxF]:
    """Why: signatures, stamps, handwriting and pictures carry PII the OCR could not read; the
    engine must be told so it can fail closed (redact or refuse) instead of trusting the text.
    What: ink mask (Otsu on a ~1200 px probe) minus padded word boxes; remaining strokes are
    merged (dilation) into regions; returns boxes in ``gray`` pixel coordinates.
    Test: a page with text plus a scribble returns one box over the scribble; text-only -> [].
    """
    small, factor = _probe(gray, _INK_PROBE_SIDE)
    array = np.asarray(small, dtype=np.uint8)
    threshold = otsu_threshold(array)
    if threshold < 40 or np.std(array) < 8:  # blank or uniform page
        return []
    ink = array < min(threshold, 200)
    pad = 3
    for x0, y0, x1, y1 in text_boxes:
        ink[max(0, int(y0 / factor) - pad): int(math.ceil(y1 / factor)) + pad,
            max(0, int(x0 / factor) - pad): int(math.ceil(x1 / factor)) + pad] = False
    if not ink.any():
        return []
    merged = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))) > 0
    side = max(array.shape)
    min_extent = max(6, side // 150)  # ~2 mm on A4: ignores dust and isolated speckles
    regions: list[BBoxF] = []
    for (x0, y0, x1, y1), _ in components(merged):
        strokes = int(np.count_nonzero(ink[y0:y1, x0:x1]))
        if max(x1 - x0, y1 - y0) >= min_extent and strokes >= min_extent * 3:
            regions.append((x0 * factor, y0 * factor, x1 * factor, y1 * factor))
    return regions


def merge_boxes(boxes: Iterable[BBox], gap: int = 0) -> list[BBox]:
    """Why: adjacent low-confidence words should be one region, not dozens of slivers.
    What: repeatedly unions boxes that overlap or are within ``gap`` pixels.
    Test: (0,0,10,10) and (12,0,20,10) with gap 3 -> [(0,0,20,10)].
    """
    pending = sorted(boxes)
    merged: list[list[int]] = []
    changed = True
    while changed:
        changed = False
        merged = []
        for box in pending:
            for target in merged:
                if box[0] <= target[2] + gap and target[0] <= box[2] + gap and box[1] <= target[3] + gap and target[1] <= box[3] + gap:
                    target[0], target[1] = min(target[0], box[0]), min(target[1], box[1])
                    target[2], target[3] = max(target[2], box[2]), max(target[3], box[3])
                    changed = True
                    break
            else:
                merged.append(list(box))
        pending = [tuple(b) for b in merged]  # type: ignore[misc]
    return [(b[0], b[1], b[2], b[3]) for b in merged]
