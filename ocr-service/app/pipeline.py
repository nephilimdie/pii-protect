"""Per-page OCR pipeline: deskew -> engine -> adaptive retry passes -> region reporting.

Fail-closed by construction: any exception on any page propagates and the API turns it into
one flat 5xx error; no partial page list is ever returned.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image

from app.config import Settings
from app.detectors.marks import MARKS, MarkWord, find_marks
from app.engines import Engine, RawWord, remaining
from app.errors import ErrorCode, OcrError
from app.imageops import PASSES, Transform, estimate_skew, ink_without_text, merge_boxes, rotate, to_gray
from app.inputs import Document, PageImage
from app.schemas import BBox, Line, OcrResponse, Page, VisualBox, Word

ENGINES = ("tesseract", "rapidocr", "auto")
MAX_REGION_SHARE = 0.25  # merged review regions never exceed a quarter of the page (no page-wide unions)


@dataclass(frozen=True)
class Attempt:
    """Why: retry passes and engines compete; the pipeline keeps the best attempt only.
    What: engine name, words in *pass* pixels, and the factor pass pixels / working pixels.
    Test: an Attempt with no words has ``mean_conf == 0`` and ``score == 0``.
    """

    engine: str
    words: list[RawWord]
    factor: float = 1.0

    @property
    def mean_conf(self) -> float:
        """Why: thresholds are expressed as confidence. What: char-weighted mean conf. Test: [] -> 0."""
        chars = sum(len(w.text) for w in self.words)
        return sum(w.conf * len(w.text) for w in self.words) / chars if chars else 0.0

    @property
    def score(self) -> float:
        """Why: a pass reading 1 word at 95 must not beat one reading 300 words at 85.
        What: number of "confident characters" (sum of conf * chars / 100).
        Test: two 5-char words at conf 80 -> 8.0.
        """
        return sum(w.conf * len(w.text) for w in self.words) / 100.0


class Pipeline:
    """Why: keeps OCR policy (engine choice, retries, region rules) out of the HTTP layer and
    engine adapters (single responsibility); engines are injected so tests can use fakes.
    What: ``run`` OCRs every page of a Document, in order, honouring the request deadline.
    Test: with a fake engine returning one word, ``run`` yields one page with one word and line.
    """

    def __init__(self, settings: Settings, engines: Mapping[str, Engine]) -> None:
        self._s = settings
        self._engines = engines

    def _engine(self, name: str) -> Engine:
        """Why: a configured-but-missing engine is an operator error, not a client one. What: lookup.
        Test: asking for an engine not in the mapping raises 503 NOT_READY.
        """
        engine = self._engines.get(name)
        if engine is None:
            raise OcrError(503, ErrorCode.NOT_READY, f"The {name} engine is not available.")
        return engine

    def _attempt(self, name: str, image: Image.Image, factor: float, lang: str, dpi: int, deadline: float) -> Attempt:
        """Why/What: one engine call on one (pre-processed) image. Test: returns the engine's words."""
        return Attempt(name, self._engine(name).recognize(image, lang, round(dpi * factor), deadline), factor)

    def _best(self, work: Image.Image, engine: str, lang: str, dpi: int, deadline: float) -> Attempt:
        """Why: clean pages should cost one engine call; only hard pages pay for retries.
        What: first engine on the deskewed page; if mean conf < adaptive threshold, retry the
        preprocessing passes (contrast, local binarize, upscale) up to ``max_passes`` total;
        in ``auto`` mode RapidOCR also competes when Tesseract stays below ``auto_fallback_conf``.
        Test: a fake engine returning conf 95 is called exactly once.
        """
        first = "rapidocr" if engine == "rapidocr" else "tesseract"
        best = self._attempt(first, work, 1.0, lang, dpi, deadline)
        for _, transform, factor in PASSES[: self._s.max_passes - 1]:
            if best.mean_conf >= self._s.adaptive_conf_threshold:
                break
            remaining(deadline)
            candidate = self._attempt(first, transform(work), factor, lang, dpi, deadline)
            best = candidate if candidate.score > best.score else best
        if engine == "auto" and best.mean_conf < self._s.auto_fallback_conf and "rapidocr" in self._engines:
            candidate = self._attempt("rapidocr", work, 1.0, lang, dpi, deadline)
            best = candidate if candidate.score > best.score else best
        return best

    def ocr_page(self, page: PageImage, engine: str, lang: str, deadline: float, marks: tuple[str, ...] = ()) -> Page:
        """Why/What: one page end-to-end; all boxes are reported in the page frame the caller
        sees (EXIF-upright, original resolution), as axis-aligned envelopes that over-cover.
        Test: a page rotated by 3 degrees yields word boxes that contain the unrotated words.
        """
        remaining(deadline)
        gray = to_gray(page.image)
        work, transform = rotate(gray, estimate_skew(gray, self._s.max_skew_degrees),
                                 Transform.identity(page.width, page.height, page.scale))
        best = self._best(work, engine, lang, page.dpi, deadline)
        if best.mean_conf < self._s.adaptive_conf_threshold:
            turned = self._upright(gray, page, engine, lang, deadline)
            if turned is not None and turned[0].score > best.score:
                best, work, transform = turned
        work_boxes = [tuple(c / best.factor for c in w.bbox) for w in best.words]
        words = [Word(text=w.text, conf=round(w.conf, 1), bbox=transform.box(b), line_id=w.line, block_id=w.block)  # type: ignore[arg-type]
                 for w, b in zip(best.words, work_boxes)]
        gap, cap = max(1, round(page.dpi / 25)), page.width * page.height * MAX_REGION_SHARE  # ~1 mm
        low_conf = merge_boxes((w.bbox for w in words if w.conf < self._s.low_conf_threshold), gap, cap)
        ink = merge_boxes((transform.box(b) for b in ink_without_text(work, work_boxes)), 0, cap)  # type: ignore[arg-type]
        found = []
        if marks:  # same decoded page and the same OCR words: no second decode or OCR pass
            remaining(deadline)
            mark_words = [MarkWord(w.text, w.conf, tuple(c / page.scale for c in w.bbox)) for w in words]  # type: ignore[misc]
            for hit in find_marks(page.image, gray, mark_words, page.dpi, self._s.low_conf_threshold, marks):
                box = (max(0, int(hit.bbox[0] * page.scale)), max(0, int(hit.bbox[1] * page.scale)),
                       min(page.width, math.ceil(hit.bbox[2] * page.scale)), min(page.height, math.ceil(hit.bbox[3] * page.scale)))
                found.append(VisualBox(type=hit.type, bbox=box, score=round(hit.score, 3), needs_review=hit.needs_review))  # type: ignore[arg-type]
        return Page(index=page.index, width=page.width, height=page.height, dpi=page.dpi, engine=best.engine,
                    words=words, lines=build_lines(words), low_conf_regions=low_conf, ink_without_text_regions=ink,
                    skew=round((transform.angle + 45) % 90 - 45, 2), marks=found)

    def _upright(self, gray: Image.Image, page: PageImage, engine: str, lang: str,
                 deadline: float) -> tuple[Attempt, Image.Image, Transform] | None:
        """Why: a sideways/upside-down page has low confidence however it is preprocessed.
        What: only for low-confidence pages, asks Tesseract OSD for a 90/180/270 turn; if confident,
        OCRs the page turned upright (plus deskew) as one rotation, so boxes still map back to the
        caller's frame. Returns None when no turn applies. Test: a page rotated 90 deg reads >= 97%.
        """
        detect = getattr(self._engines.get("tesseract"), "orientation", None)
        if detect is None:
            return None
        turned, confidence = detect(gray, deadline)
        if turned not in (90, 180, 270) or confidence < self._s.osd_min_confidence:
            return None
        upright = gray.rotate(-turned, expand=True)  # exact for right angles
        angle = -turned + estimate_skew(upright, self._s.max_skew_degrees)
        work, transform = rotate(gray, angle, Transform.identity(page.width, page.height, page.scale))
        return self._best(work, engine, lang, page.dpi, deadline), work, transform

    def run(self, document: Document, engine: str, lang: str, deadline: float, marks: tuple[str, ...] = ()) -> OcrResponse:
        """Why/What: OCR all pages in order, one bitmap alive at a time. Test: see class."""
        return OcrResponse(pages=[self.ocr_page(page, engine, lang, deadline, marks) for page in document.pages()])


def parse_marks(raw: str | None) -> tuple[str, ...]:
    """Why: the ``marks`` field is untrusted. What: comma list -> ordered subset of MARKS
    (empty/absent -> none: older callers get the unchanged response). Test: "stamp,signature"
    -> ("signature", "stamp"); "logo" -> 422 INVALID_PARAMETER.
    """
    wanted = {part.strip() for part in (raw or "").split(",") if part.strip()}
    if not wanted <= set(MARKS):
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"marks must be a comma list of {list(MARKS)}.")
    return tuple(name for name in MARKS if name in wanted)


def build_lines(words: list[Word]) -> list[Line]:
    """Why: PII spans words; lines give the engine text + reading order without re-grouping.
    What: groups words by ``line_id`` (first-seen order); box is the union of word boxes.
    Test: words "Mario"(line 0) and "Rossi"(line 0) -> one Line "Mario Rossi".
    """
    grouped: dict[int, list[Word]] = {}
    for word in words:
        grouped.setdefault(word.line_id, []).append(word)
    lines: list[Line] = []
    for line_id, members in grouped.items():
        box: BBox = (min(w.bbox[0] for w in members), min(w.bbox[1] for w in members),
                     max(w.bbox[2] for w in members), max(w.bbox[3] for w in members))
        lines.append(Line(id=line_id, bbox=box, text=" ".join(w.text for w in members)))
    return lines
