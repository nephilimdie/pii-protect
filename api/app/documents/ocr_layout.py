"""OCR result -> page text for detection, and detected char spans -> pixel boxes to redact."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.documents.models import SegmentEdit
from app.documents.ocr_client import BBox, OcrResult, VisualHit

MIN_PAD_PX = 3
LINE_PAD = 0.15  # of the line height, on every side
REVIEW_REASONS = ("low_confidence", "unrecognized_ink")
TILT_MIN_DEG = 0.5  # below this a page counts as straight
TILT_ERROR_DEG = 1.0  # assumed error of the service's skew estimate
TILT_END_PAD = 0.3  # of the line height, left/right: a first/last glyph clipped by a tilted word box
STYLE_CELLS = 8  # pixelate/blur keep at most 8 x 8 colour cells of a face (no identity survives that)
STYLE_NOISE = 24  # +/- per cell and channel, fresh OS randomness on every render
STYLE_LEVELS = 16  # cell colours are then quantized to multiples of 16


class FaceStyle(StrEnum):
    """How faces are hidden. BLACK (default) is the safest: nothing of the face survives."""

    BLACK = "black"
    PIXELATE = "pixelate"
    BLUR = "blur"


def _inside(inner: BBox, outer: BBox) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


@dataclass(frozen=True)
class _WordSpan:
    start: int
    end: int
    line: int
    bbox: BBox


@dataclass(frozen=True)
class ScannedPage:
    """Why: detection works on text, redaction on pixels; both must agree character by character.
    What: page text built from OCR lines (words joined by spaces, lines by "\\n", blocks by a
    blank line) with each word's char span and box, plus the fail-closed review regions
    (low-confidence and ink-without-text, minus those wholly inside a signature/stamp) and
    visual hits (faces, codes, plates, signatures, stamps), all in the
    pixels of the OCR'd image, plus the page ``skew`` (degrees) used to pad tilted boxes.
    Test: words "Mario" "Rossi" on one line -> text "Mario Rossi"; boxes(0, 11) is one box
    spanning both words; boxes(6, 8) is the box of "Rossi" only.
    """

    width: int
    height: int
    text: str
    spans: tuple[_WordSpan, ...]
    review: tuple[tuple[str, BBox], ...]
    visual: tuple[VisualHit, ...] = ()
    skew: float = 0.0

    @classmethod
    def from_ocr(cls, result: OcrResult, visual: list[VisualHit] | None = None) -> ScannedPage:
        by_line: dict[int, list] = {}
        for word in result.words:
            if word.text.strip():
                by_line.setdefault(word.line_id, []).append(word)
        listed = [line for line in dict.fromkeys(result.line_order) if line in by_line]
        order = listed + [line for line in by_line if line not in set(listed)]
        parts: list[str] = []
        spans: list[_WordSpan] = []
        cursor, block = 0, None
        for n, line in enumerate(order):
            words = by_line[line]
            if n:
                separator = "\n" if words[0].block_id == block else "\n\n"
                parts.append(separator)
                cursor += len(separator)
            for k, word in enumerate(words):
                if k:
                    parts.append(" ")
                    cursor += 1
                token = " ".join(word.text.split())
                spans.append(_WordSpan(cursor, cursor + len(token), line, word.bbox))
                parts.append(token)
                cursor += len(token)
            block = words[-1].block_id
        # a review region wholly inside a signature/stamp box is painted by that mark anyway
        marks = [hit.bbox for hit in result.marks]
        review = tuple((reason, box) for reason, boxes in zip(REVIEW_REASONS, (result.low_conf_regions, result.ink_regions))
                       for box in boxes if not any(_inside(box, mark) for mark in marks))
        return cls(result.width, result.height, "".join(parts), tuple(spans), review,
                   (*(visual or ()), *result.marks), result.skew)

    def boxes(self, start: int, end: int) -> list[BBox]:
        """One box per line segment covering every word that overlaps [start, end) (whole words)."""
        lines: dict[int, list[int]] = {}
        for span in self.spans:
            if span.start < end and span.end > start:
                box = lines.setdefault(span.line, list(span.bbox))
                box[0], box[1] = min(box[0], span.bbox[0]), min(box[1], span.bbox[1])
                box[2], box[3] = max(box[2], span.bbox[2]), max(box[3], span.bbox[3])
        return [(b[0], b[1], b[2], b[3]) for b in lines.values()]

    def normalized(self, box: BBox) -> list[float]:
        """Box as fractions of the displayed page (top-left origin), for drawing in any viewer."""
        return [round(box[0] / self.width, 5), round(box[1] / self.height, 5),
                round(box[2] / self.width, 5), round(box[3] / self.height, 5)]


def to_device(box: BBox, fx: float, fy: float, width: int, height: int, line: bool, skew: float = 0.0) -> BBox:
    """Why: OCR ran at its own DPI; the output page is rendered at the document DPI. On tilted
    photos the straightened word boxes can clip the first/last glyph (seen on prod: a sliver of
    a phone number's last digit), and the skew estimate itself has ~1 degree of error.
    What: scales an OCR-pixel box to output pixels and pads it (lines: 15% of the line height,
    at least MIN_PAD_PX; regions: MIN_PAD_PX), clipped to the image. Lines on a page tilted by
    >= TILT_MIN_DEG also get TILT_END_PAD of the line height left/right and half the box width
    times sin(TILT_ERROR_DEG) above/below.
    Test: (10, 10, 20, 30) at fx=fy=0.5 -> height 10 -> pad 3 -> (2, 2, 13, 18); with skew=3 a
    (0, 100, 1000, 140) line gains 12 px left/right and 9 px above/below.
    """
    x0, y0, x1, y1 = math.floor(box[0] * fx), math.floor(box[1] * fy), math.ceil(box[2] * fx), math.ceil(box[3] * fy)
    pad = max(MIN_PAD_PX, math.ceil(LINE_PAD * (y1 - y0))) if line else MIN_PAD_PX
    px = py = pad
    if line and abs(skew) >= TILT_MIN_DEG:
        px += math.ceil(TILT_END_PAD * (y1 - y0))
        py += math.ceil((x1 - x0) / 2 * math.sin(math.radians(TILT_ERROR_DEG)))
    return max(0, x0 - px), max(0, y0 - py), min(width, x1 + px), min(height, y1 + py)


class ScannedPages:
    """Why: scanned PDF pages and images share one review contract (boxes as page fractions,
    numbered needs_review regions, fail-closed painting); one implementation keeps them equal.
    What: mixin over ``self.scanned`` ({0-based page: ScannedPage}): entity_boxes(), review_boxes()
    and review_by_page(keep) (the regions still to paint after the user's review_keep).
    Test: test_documents_ocr.py / test_documents_image.py preview payloads (ids, pages, bboxes).
    """

    scanned: dict[int, ScannedPage]

    def entity_boxes(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """Boxes of an entity on scanned pages: [{page (1-based), bbox: normalized [x0,y0,x1,y1]}]."""
        out = []
        for segment, start, end in pieces:
            page = self.scanned.get(segment)
            if page is not None:
                out.extend({"page": segment + 1, "bbox": page.normalized(box)} for box in page.boxes(start, end))
        return out

    def review_boxes(self) -> list[dict]:
        """Fail-closed regions (always redacted unless kept by id): low-confidence text, unread ink."""
        boxes = []
        for index in sorted(self.scanned):
            page = self.scanned[index]
            boxes.extend({"page": index + 1, "reason": reason, "bbox": page.normalized(box)}
                         for reason, box in page.review)
        return [{"id": n, **box} for n, box in enumerate(boxes)]

    def visual_entities(self) -> list[dict]:
        """Faces, codes, plates, signatures, stamps (always painted; ``needs_review`` = worth a human look)."""
        out = []
        for index in sorted(self.scanned):
            page = self.scanned[index]
            out.extend({"type": hit.type, "page": index + 1, "bbox": page.normalized(hit.bbox),
                        "score": round(hit.score, 3), "needs_review": hit.needs_review} for hit in page.visual)
        return [{"id": n, **hit} for n, hit in enumerate(out)]

    def visual_types(self) -> set[str]:
        return {hit.type for page in self.scanned.values() for hit in page.visual}

    def review_by_page(self, keep: frozenset[int]) -> dict[int, list[BBox]]:
        out: dict[int, list[BBox]] = defaultdict(list)
        n = 0
        for index in sorted(self.scanned):
            for _, box in self.scanned[index].review:
                if n not in keep:
                    out[index].append(box)
                n += 1
        return out


def obscure(image: Image.Image, box: BBox, style: str) -> None:
    """Why: some users want a face to read as "a person" instead of a black box, but a mosaic
    or blur must never be reversible (deblurring and super-resolution recover small mosaics).
    What: replaces the box with at most STYLE_CELLS x STYLE_CELLS cell colours (box average;
    BLUR first blurs with a radius of 1/4 of the box), each shifted by +/-STYLE_NOISE of fresh
    OS randomness and quantized to STYLE_LEVELS, then enlarged (PIXELATE: hard blocks; BLUR:
    smooth). At most 64 noisy, quantized colours remain of any face. Mutates ``image``.
    Test: test_documents_visual.py: a pixelated face has <= 64 colours and nothing finer than
    its cell grid; a blurred one has almost no edge energy; two renders differ (fresh noise).
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    region = image.crop(box)
    if style == FaceStyle.BLUR:
        region = region.filter(ImageFilter.GaussianBlur(max(w, h) / 4))
    longest = max(w, h)
    cells = (max(1, round(STYLE_CELLS * w / longest)), max(1, round(STYLE_CELLS * h / longest)))
    grid = np.asarray(region.resize(cells, Image.Resampling.BOX), dtype=np.int16)
    grid = grid + np.random.default_rng().integers(-STYLE_NOISE, STYLE_NOISE + 1, grid.shape)
    grid = (np.clip(grid, 0, 255) // STYLE_LEVELS * STYLE_LEVELS + STYLE_LEVELS // 2).astype(np.uint8)
    small = Image.fromarray(grid, "RGB")
    if style == FaceStyle.PIXELATE:
        out = small.resize((w, h), Image.Resampling.NEAREST)
    else:
        out = small.resize((w, h), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(longest / STYLE_CELLS / 2))
    image.paste(out, (x0, y0))


def paint(image: Image.Image, page: ScannedPage, edits: list[SegmentEdit], review: list[BBox],
          face_style: str = FaceStyle.BLACK) -> None:
    """Why: the only thing that hides PII in a scan is opaque pixels over the OCR boxes.
    What: paints solid black over every edited span's line boxes, every review region and every
    visual hit (faces, codes, plates, signatures, stamps: never optional), scaled from the
    OCR'd image to ``image`` and padded (to_device, tilt-aware for lines). With ``face_style``
    pixelate/blur, FACE boxes are obscured irreversibly instead (see obscure); anything black
    that overlaps a face stays black on top. Mutates ``image`` (RGB).
    Test: an edit over "Mario Rossi" -> mean pixel value in the word box < 20.
    """
    fx, fy = image.width / page.width, image.height / page.height
    draw = ImageDraw.Draw(image)
    styled = face_style != FaceStyle.BLACK
    boxes = [(box, True) for edit in edits for box in page.boxes(edit.start, edit.end)]
    boxes += [(box, False) for box in [*review, *(hit.bbox for hit in page.visual if not (styled and hit.type == "FACE"))]]
    if styled:
        for hit in page.visual:
            if hit.type == "FACE":
                x0, y0, x1, y1 = to_device(hit.bbox, fx, fy, image.width, image.height, False)
                if x1 > x0 and y1 > y0:
                    obscure(image, (x0, y0, x1, y1), face_style)
    for box, line in boxes:
        x0, y0, x1, y1 = to_device(box, fx, fy, image.width, image.height, line, page.skew)
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
