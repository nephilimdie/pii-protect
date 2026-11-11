"""OCR result -> page text for detection, and detected char spans -> pixel boxes to redact."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from PIL import Image, ImageFilter

from app.documents.models import SegmentEdit
from app.documents.ocr_client import BBox, OcrResult, VisualHit
from app.documents.redaction_style import Run, label_for, paint_area, paint_pills

MIN_PAD_PX = 3
LINE_PAD = 0.15  # of the line height, on every side
REVIEW_REASONS = ("low_confidence", "unrecognized_ink")
UNCERTAIN_MARK = "uncertain_mark"  # review reason of a signature/stamp the service is not sure about
UNCERTAIN_CODE = "uncertain_code"  # invalid code whose locator covers too much of the image
MAX_UNCERTAIN_CODE_SHARE = 0.5
TILT_MIN_DEG = 0.5  # below this a page counts as straight
TILT_ERROR_DEG = 1.0  # assumed error of the service's skew estimate
TILT_END_PAD = 0.3  # of the line height, left/right: a first/last glyph clipped by a tilted word box
STYLE_CELLS = 8  # pixelate/blur keep at most 8 x 8 colour cells of a face (no identity survives that)
STYLE_NOISE = 24  # pixelate: +/- per cell and channel, fresh OS randomness
STYLE_LEVELS = 16  # pixelate: cell colours quantized to multiples of 16
BLUR_CELLS = 12  # blur: at most 12 cells across the face (soft, still no identity: noise + quantization)
BLUR_NOISE = 10  # +/- one luminance shift per blur cell
BLUR_LEVELS = 8  # blur cell colours quantized to multiples of 8
BLUR_AXIS = 0.6  # blur ellipse semi-axes as a share of the face box sides (just past the inscribed oval)
BLUR_FEATHER = 0.15  # of the face's longest side: the soft edge where the blur fades into the photo
BLUR_GRAIN = 2.0  # sigma of per-pixel grain on the blur (adds no face information)
INK_DELTA = 40  # glyph_band: a pixel this far from its word box's median grey is ink
FACE_ABSORB = 0.5  # a review region at least half inside a face box grown by 50% per side is the face's own ink


class FaceStyle(StrEnum):
    """How faces are hidden. BLACK (default) is the safest: nothing of the face survives."""

    BLACK = "black"
    PIXELATE = "pixelate"
    BLUR = "blur"


def _grown(box: BBox, share: float) -> BBox:
    dx, dy = (box[2] - box[0]) * share, (box[3] - box[1]) * share
    return box[0] - dx, box[1] - dy, box[2] + dx, box[3] + dy


def _overlap(box: BBox, other: BBox) -> float:
    """Share of ``box``'s area inside ``other``."""
    w = min(box[2], other[2]) - max(box[0], other[0])
    h = min(box[3], other[3]) - max(box[1], other[1])
    area = (box[2] - box[0]) * (box[3] - box[1])
    return w * h / area if w > 0 and h > 0 and area > 0 else 0.0


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
    blank line) with each word's char span and box, plus the review regions (low-confidence and
    ink-without-text, minus those wholly inside a signature/stamp, then the signatures/stamps the
    service marked needs_review) and visual hits (faces, codes, plates, sure signatures/stamps), all in the
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
        # a review region wholly inside a signature/stamp box goes with that mark: painted with a sure
        # one; with an uncertain one (itself a review region, listed last) covered or shown together
        # likewise one mostly around a face (hair, eyes) or holding a whole face (a portrait photo on a
        # form) is that face's own picture: the face is obscured anyway, and painting the rest black
        # would frame the blurred face in a black box (founder, 2026-11-09)
        marks = [hit.bbox for hit in result.marks]
        faces = [hit.bbox for hit in visual or () if hit.type == "FACE"]
        large_codes = [hit for hit in visual or () if hit.type == "BARCODE" and hit.needs_review
                       and (hit.bbox[2] - hit.bbox[0]) * (hit.bbox[3] - hit.bbox[1])
                       >= MAX_UNCERTAIN_CODE_SHARE * result.width * result.height]
        review = tuple((reason, box) for reason, boxes in zip(REVIEW_REASONS, (result.low_conf_regions, result.ink_regions))
                       for box in boxes if not any(_inside(box, mark) for mark in marks)
                       and not any(_overlap(box, _grown(face, FACE_ABSORB)) >= 0.5 or _inside(face, box) for face in faces))
        review += tuple((UNCERTAIN_MARK, hit.bbox) for hit in result.marks if hit.needs_review)
        review += tuple((UNCERTAIN_CODE, hit.bbox) for hit in large_codes)
        return cls(result.width, result.height, "".join(parts), tuple(spans), review,
                   (*(hit for hit in visual or () if hit not in large_codes),
                    *(hit for hit in result.marks if not hit.needs_review)), result.skew)

    def boxes(self, start: int, end: int) -> list[BBox]:
        """Boxes of the text in [start, end) (see line_boxes), without their line ids."""
        return [box for _, box in self.line_boxes(start, end)]

    def line_boxes(self, start: int, end: int) -> list[tuple[int, BBox]]:
        """Cover whole OCR words, joining only neighbours rather than spanning a column gap.

        OCR occasionally puts text from distant columns in the same logical line. A single
        union box then hides everything between them. Gaps up to half a word height are
        merged so ordinary spaces in a name do not disclose individual word lengths.
        Returns (OCR line id, box) pairs.
        """
        lines: dict[int, list[BBox]] = defaultdict(list)
        for span in self.spans:
            if span.start < end and span.end > start:
                lines[span.line].append(span.bbox)
        out: list[tuple[int, BBox]] = []
        for line, words in lines.items():
            merged: list[int] | None = None
            for box in sorted(words, key=lambda b: (b[0], b[1])):
                if merged is not None:
                    gap = box[0] - merged[2]
                    height = max(merged[3] - merged[1], box[3] - box[1])
                    overlap_y = min(merged[3], box[3]) - max(merged[1], box[1])
                    if overlap_y > 0 and gap <= height / 2:
                        merged[0] = min(merged[0], box[0])
                        merged[1] = min(merged[1], box[1])
                        merged[2] = max(merged[2], box[2])
                        merged[3] = max(merged[3], box[3])
                        continue
                    out.append((line, tuple(merged)))
                merged = list(box)
            if merged is not None:
                out.append((line, tuple(merged)))
        return out

    def normalized(self, box: BBox) -> list[float]:
        """Box as fractions of the displayed page (top-left origin), for drawing in any viewer."""
        return [round(box[0] / self.width, 5), round(box[1] / self.height, 5),
                round(box[2] / self.width, 5), round(box[3] / self.height, 5)]


def to_device(box: BBox, fx: float, fy: float, width: int, height: int, line: bool, skew: float = 0.0,
              band: tuple[int, int] | None = None) -> BBox:
    """Why: OCR ran at its own DPI; the output page is rendered at the document DPI. On tilted
    photos the straightened word boxes can clip the first/last glyph (seen on prod: a sliver of
    a phone number's last digit), and the skew estimate itself has ~1 degree of error.
    What: scales an OCR-pixel box to output pixels and pads it (lines: 15% of the line height,
    at least MIN_PAD_PX; regions: MIN_PAD_PX), clipped to the image. Lines on a page tilted by
    >= TILT_MIN_DEG also get TILT_END_PAD of the line height left/right and half the box width
    times sin(TILT_ERROR_DEG) above/below.
    A line's ``band`` (output pixels: the glyph rows measured by glyph_band) replaces the OCR box's
    vertical extent, its height sets the vertical pad; left/right pads still follow the OCR box.
    Test: (10, 10, 20, 30) at fx=fy=0.5 -> height 10 -> pad 3 -> (2, 2, 13, 18); with skew=3 a
    (0, 100, 1000, 140) line gains 12 px left/right and 9 px above/below.
    """
    x0, y0, x1, y1 = math.floor(box[0] * fx), math.floor(box[1] * fy), math.ceil(box[2] * fx), math.ceil(box[3] * fy)
    box_height = y1 - y0
    px = max(MIN_PAD_PX, math.ceil(LINE_PAD * box_height)) if line else MIN_PAD_PX
    if line and band is not None:
        y0, y1 = band
    py = max(MIN_PAD_PX, math.ceil(LINE_PAD * (y1 - y0))) if line else MIN_PAD_PX
    if line and abs(skew) >= TILT_MIN_DEG:
        px += math.ceil(TILT_END_PAD * box_height)
        py += math.ceil((x1 - x0) / 2 * math.sin(math.radians(TILT_ERROR_DEG)))
    return max(0, x0 - px), max(0, y0 - py), min(width, x1 + px), min(height, y1 + py)


def glyph_band(gray: np.ndarray, box: BBox) -> tuple[int, int]:
    """Why: detector-based OCR boxes are ~1.7x the glyph height; covers that size fuse adjacent
    lines into one slab (founder, ID-card sample 2026-11-10). Only rows proven empty may be dropped.
    What: the rows of ``box`` (output pixels) holding ink, i.e. pixels at least INK_DELTA away
    from the box's median (its background), plus one row of slack each side; the whole box when
    nothing qualifies (faint text, busy background, ink touching an edge keeps that edge).
    Test: a 40 px box with ink in rows 12-28 -> (11, 30); a blank box -> unchanged.
    """
    x0, y0, x1, y1 = box
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return y0, y1
    rows = np.flatnonzero((np.abs(crop - np.median(crop)) >= INK_DELTA).any(axis=1))
    if rows.size == 0:
        return y0, y1
    return y0 + max(0, int(rows[0]) - 1), y0 + min(crop.shape[0], int(rows[-1]) + 2)


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

    def visual_keep_by_page(self, keep: frozenset[int]) -> dict[int, frozenset[int]]:
        """Map globally numbered visual IDs to each scanned page's local hit indexes."""
        out: dict[int, frozenset[int]] = {}
        next_id = 0
        for index in sorted(self.scanned):
            count = len(self.scanned[index].visual)
            out[index] = frozenset(i for i in range(count) if next_id + i in keep)
            next_id += count
        return out

    def review_by_page(self, keep: frozenset[int]) -> dict[int, list[BBox]]:
        out: dict[int, list[BBox]] = defaultdict(list)
        n = 0
        for index in sorted(self.scanned):
            for _, box in self.scanned[index].review:
                if n not in keep:
                    out[index].append(box)
                n += 1
        return out


Frac = tuple[float, float, float, float]  # a box as fractions of the displayed page (x0, y0, x1, y1)
Covers = Mapping[int, Sequence[Frac]]  # user-drawn areas to paint, by 0-based page


def _cells(region: Image.Image, cells: tuple[int, int], rng: np.random.Generator, noise: int, levels: int,
           shared: bool) -> Image.Image:
    """``region`` as ``cells`` box averages, +/-``noise`` (``shared``: one shift for R, G and B, so no
    colour blotches), quantized to multiples of ``levels``."""
    grid = np.asarray(region.resize(cells, Image.Resampling.BOX), dtype=np.int16)
    grid = grid + rng.integers(-noise, noise + 1, grid.shape[:2] if shared else grid.shape).reshape((*grid.shape[:2], -1))
    return Image.fromarray((np.clip(grid, 0, 255) // levels * levels + levels // 2).astype(np.uint8), "RGB")


def obscure(image: Image.Image, box: BBox, style: str) -> tuple[Image.Image, Image.Image | None, tuple[int, int]]:
    """Why: some users want a face to read as "a person" instead of a black box, but a mosaic
    or blur must never be reversible (deblurring and super-resolution recover small mosaics).
    What: computes, from ``image``'s ORIGINAL pixels, a (tile, footprint mask, origin) to paste.
    PIXELATE: the box as at most STYLE_CELLS x STYLE_CELLS hard blocks (per-channel noise,
    quantized), no mask. BLUR: a soft oval (semi-axes BLUR_AXIS of the box sides, BLUR_FEATHER
    edge) of at most BLUR_CELLS cells across the face (lightly pre-blurred box averages, one
    noisy quantized luminance shift per cell), smoothly enlarged, fine grain, already blended
    over the original photo, so pasted over anything (e.g. a covered review region) it never
    shows a black underlay; the mask is its footprint. Fresh OS randomness on every call.
    Test: test_documents_visual.py: a pixelated face has <= 64 colours; a blurred one has no
    edge energy inside the oval, fades into the photo (no hard edge, no black), far pixels intact.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    longest = max(w, h, 1)
    rng = np.random.default_rng()
    if style == FaceStyle.PIXELATE:
        cells = (max(1, round(STYLE_CELLS * w / longest)), max(1, round(STYLE_CELLS * h / longest)))
        tile = _cells(image.crop(box), cells, rng, STYLE_NOISE, STYLE_LEVELS, False)
        return tile.resize((w, h), Image.Resampling.NEAREST), None, (x0, y0)
    cx, cy, ax, ay = (x0 + x1) / 2, (y0 + y1) / 2, max(w, 1) * BLUR_AXIS, max(h, 1) * BLUR_AXIS
    feather = BLUR_FEATHER * longest
    ox0, oy0 = max(0, math.floor(cx - ax - feather)), max(0, math.floor(cy - ay - feather))
    ox1, oy1 = min(image.width, math.ceil(cx + ax + feather)), min(image.height, math.ceil(cy + ay + feather))
    region = image.crop((ox0, oy0, ox1, oy1))
    cell = longest / BLUR_CELLS
    cells = (max(1, round(region.width / cell)), max(1, round(region.height / cell)))
    small = _cells(region.filter(ImageFilter.GaussianBlur(cell / 2)), cells, rng, BLUR_NOISE, BLUR_LEVELS, True)
    smooth = small.resize(region.size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(cell * 0.6))
    blurred = np.asarray(smooth, dtype=np.float32) + rng.normal(0, BLUR_GRAIN, (region.height, region.width, 1))
    yy, xx = np.mgrid[oy0:oy1, ox0:ox1].astype(np.float32) + 0.5
    outside = (np.hypot((xx - cx) / ax, (yy - cy) / ay) - 1) * min(ax, ay) / feather  # 0 on the ellipse, 1 at the fade end
    alpha = np.clip(1 - outside, 0, 1)
    alpha = (alpha * alpha * (3 - 2 * alpha))[..., None]
    mixed = blurred * alpha + np.asarray(region, dtype=np.float32) * (1 - alpha)  # over the photo, never over black
    tile = Image.fromarray(np.clip(mixed, 0, 255).astype(np.uint8), "RGB")
    return tile, Image.fromarray(np.where(alpha[..., 0] > 0, 255, 0).astype(np.uint8), "L"), (ox0, oy0)


def cover_pixels(cover: Sequence[Frac], width: int, height: int) -> list[BBox]:
    """User-drawn areas (page fractions) -> pixel boxes padded by MIN_PAD_PX, clipped (empty ones dropped)."""
    out = []
    for x0, y0, x1, y1 in cover:
        box = (max(0, math.floor(x0 * width) - MIN_PAD_PX), max(0, math.floor(y0 * height) - MIN_PAD_PX),
               min(width, math.ceil(x1 * width) + MIN_PAD_PX), min(height, math.ceil(y1 * height) + MIN_PAD_PX))
        if box[2] > box[0] and box[3] > box[1]:
            out.append(box)
    return out


def text_runs(page: ScannedPage, edits: list[SegmentEdit], gray: np.ndarray, fx: float,
              fy: float) -> tuple[list[Run], list[BBox]]:
    """Why: text covers must hug the glyphs of each line (not the loose OCR box) and know which
    visible words sit next to them. What: (one Run per edited line box: to_device-padded, tilt-aware,
    vertical band = union of glyph_band over the edited words of that OCR line, labelled with the entity
    type; output-pixel boxes of the words no edit touches). ``gray``: the ORIGINAL pixels.
    Test: an edit over one word of a line whose OCR box is twice the glyph height -> the run's band
    is the glyph rows plus padding, not the OCR box.
    """
    height, width = gray.shape

    def scaled(box: BBox) -> BBox:
        return (math.floor(box[0] * fx), math.floor(box[1] * fy),
                min(width, math.ceil(box[2] * fx)), min(height, math.ceil(box[3] * fy)))

    runs = []
    for edit in edits:
        for line, box in page.line_boxes(edit.start, edit.end):
            rows = [glyph_band(gray, scaled(span.bbox)) for span in page.spans
                    if span.line == line and span.start < edit.end and span.end > edit.start]
            band = (min(r[0] for r in rows), max(r[1] for r in rows))
            x0, y0, x1, y1 = to_device(box, fx, fy, width, height, True, page.skew, band)
            if x1 > x0 and y1 > y0:
                runs.append(Run(x0, y0, x1, y1, band[1] - band[0], label_for(edit.label)))
    shown = [scaled(span.bbox) for span in page.spans
             if not any(span.start < edit.end and span.end > edit.start for edit in edits)]
    return runs, shown


def paint(image: Image.Image, page: ScannedPage, edits: list[SegmentEdit], review: list[BBox],
          face_style: str = FaceStyle.BLACK, cover: Sequence[Frac] = (),
          keep_visual: frozenset[int] = frozenset(), show_labels: bool = True) -> None:
    """Why: the only thing that hides PII in a scan is opaque pixels over the OCR boxes.
    What: paints opaque covers (redaction_style: indigo pills/areas) over the given review regions,
    every visual hit (faces, codes, plates, sure signatures and stamps: never optional), every
    edited span (one pill per line run, see text_runs / pill_boxes) and the user's ``cover`` areas
    (fractions of the page), scaled from the OCR'd image to ``image`` and padded (to_device,
    tilt-aware for lines). With ``face_style`` pixelate/blur, FACE boxes are obscured irreversibly
    instead (see obscure), from the original pixels and on top of review regions; text PII, codes,
    plates, marks and user areas stay covered on top. Mutates ``image`` (RGB).
    Test: an edit over "Mario Rossi" -> every pixel of the padded word box is cover fill.
    """
    fx, fy = image.width / page.width, image.height / page.height
    gray = np.asarray(image.convert("L"), dtype=np.int16)  # measured before any cover is painted
    runs, shown = text_runs(page, edits, gray, fx, fy)

    def device(box: BBox) -> BBox:
        return to_device(box, fx, fy, image.width, image.height, False)

    visual = [hit for i, hit in enumerate(page.visual) if i not in keep_visual]
    styled = face_style != FaceStyle.BLACK
    faces = [device(h.bbox) for h in visual if styled and h.type == "FACE"]
    # obscured from the ORIGINAL pixels, then pasted over the review regions (on photos the unread-ink
    # region usually overlaps the face): nothing readable survives inside a face box either way
    obscured = [obscure(image, box, face_style) for box in faces if box[2] > box[0] and box[3] > box[1]]
    for box in review:
        paint_area(image, device(box))
    for tile, mask, origin in obscured:
        image.paste(tile, origin, mask)
    for hit in visual:  # codes, plates, marks (and faces, unless styled)
        if not (styled and hit.type == "FACE"):
            paint_area(image, device(hit.bbox), label_for(hit.type), show_labels)
    paint_pills(image, runs, shown, show_labels)  # text PII: always on top
    for box in cover_pixels(cover, image.width, image.height):
        paint_area(image, box)
