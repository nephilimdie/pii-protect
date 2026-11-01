"""OCR result -> page text for detection, and detected char spans -> pixel boxes to redact."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.documents.models import SegmentEdit
from app.documents.ocr_client import BBox, OcrResult

MIN_PAD_PX = 3
LINE_PAD = 0.15  # of the line height, on every side
REVIEW_REASONS = ("low_confidence", "unrecognized_ink")


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
    (low-confidence and ink-without-text), all in the pixels of the OCR'd image.
    Test: words "Mario" "Rossi" on one line -> text "Mario Rossi"; boxes(0, 11) is one box
    spanning both words; boxes(6, 8) is the box of "Rossi" only.
    """

    width: int
    height: int
    text: str
    spans: tuple[_WordSpan, ...]
    review: tuple[tuple[str, BBox], ...]

    @classmethod
    def from_ocr(cls, result: OcrResult) -> ScannedPage:
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
        review = tuple([(REVIEW_REASONS[0], box) for box in result.low_conf_regions]
                       + [(REVIEW_REASONS[1], box) for box in result.ink_regions])
        return cls(result.width, result.height, "".join(parts), tuple(spans), review)

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


def to_device(box: BBox, fx: float, fy: float, width: int, height: int, line: bool) -> BBox:
    """Why: OCR ran at its own DPI; the output page is rendered at the document DPI.
    What: scales an OCR-pixel box to output pixels and pads it (lines: 15% of the line height,
    at least MIN_PAD_PX; regions: MIN_PAD_PX), clipped to the image.
    Test: (10, 10, 20, 30) at fx=fy=0.5 -> height 10 -> pad 3 -> (2, 2, 13, 18).
    """
    x0, y0, x1, y1 = math.floor(box[0] * fx), math.floor(box[1] * fy), math.ceil(box[2] * fx), math.ceil(box[3] * fy)
    pad = max(MIN_PAD_PX, math.ceil(LINE_PAD * (y1 - y0))) if line else MIN_PAD_PX
    return max(0, x0 - pad), max(0, y0 - pad), min(width, x1 + pad), min(height, y1 + pad)


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

    def review_by_page(self, keep: frozenset[int]) -> dict[int, list[BBox]]:
        out: dict[int, list[BBox]] = defaultdict(list)
        n = 0
        for index in sorted(self.scanned):
            for _, box in self.scanned[index].review:
                if n not in keep:
                    out[index].append(box)
                n += 1
        return out


def paint(image: Image.Image, page: ScannedPage, edits: list[SegmentEdit], review: list[BBox]) -> None:
    """Why: the only thing that hides PII in a scan is opaque pixels over the OCR boxes.
    What: paints solid black over every edited span's line boxes and every review region,
    scaled from the OCR'd image to ``image`` and padded (to_device). Mutates ``image`` (RGB).
    Test: an edit over "Mario Rossi" -> mean pixel value in the word box < 20.
    """
    fx, fy = image.width / page.width, image.height / page.height
    draw = ImageDraw.Draw(image)
    boxes = [(box, True) for edit in edits for box in page.boxes(edit.start, edit.end)]
    boxes += [(box, False) for box in review]
    for box, line in boxes:
        x0, y0, x1, y1 = to_device(box, fx, fy, image.width, image.height, line)
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
