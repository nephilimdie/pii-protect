"""The look of every opaque cover the engine paints on images and flattened PDF pages.

Tokens are documented in doc/redaction-style.md (clients drawing their own covers match them).
Geometry rules (security first, then looks):
- a text cover ("pill") is one shape per line run, its height normalized per line, its width
  rounded UP to a bucket of the line's glyph height (plus a small jitter that depends only on the
  bucket), so the cover never tells how many characters it hides; it always contains the padded
  box it was asked to cover (rounded ends are added outside it), clipped to the image;
- an area (uncertain region, face, code, plate, signature, stamp, user area) keeps its geometry,
  grown just enough that its rounded corners still contain the whole box;
- every pixel inside a shape is opaque fill: nothing of the original survives inside.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BBox = tuple[int, int, int, int]

COVER_FILL = (35, 34, 68)  # opaque, restrained indigo; also used by the cover audit
RIM = (72, 70, 120)  # subtle edge separates adjacent covers without a striped texture
RIM_MIX = 0.18
LABEL_INK = (238, 240, 255)  # #EEF0FF: entity-type label
PILL_RADIUS = 0.35  # keep established cover geometry; changing it affects merge/sizing rules
AREA_RADIUS = 0.12
AREA_RADIUS_MAX = 14
BUCKET = 1.5  # pill widths are multiples of 1.5 x the line's glyph height
JITTER = 0.2  # + up to 0.2 x glyph height, a function of the bucket only
LABEL_SIZE = 0.42  # label font size, of the pill height
LABEL_MIN_PX = 9  # smaller labels are not drawn
SUPERSAMPLE = 4  # anti-aliased rounded edges
COVER_BLUE = 8  # cover_share: every cover colour has blue >= 8 above red and green
SAME_LINE = 0.5  # runs whose band centres are closer than half a glyph height share a line
MAX_LINE_GLYPH_RATIO = 2.0  # handwriting must not join much smaller printed fields below it
NEIGHBOUR_GAP = 0.25  # of the glyph height: room kept before a visible neighbouring word

# entity type -> short Italian label; types not listed get no label (never the content)
LABELS = {
    "PERSON": "NOME", "FISCAL_CODE": "CF", "DATE": "DATA", "DATE_OF_BIRTH": "DATA", "IBAN": "IBAN",
    "ADDRESS": "INDIRIZZO", "LOCATION": "LUOGO", "PHONE": "TEL", "EMAIL": "EMAIL", "CREDIT_CARD": "CARTA",
    "CVV": "CVV", "IDENTITY_CARD": "DOCUMENTO", "PASSPORT": "PASSAPORTO", "DRIVER_LICENSE": "PATENTE",
    "ACCOUNT_NUMBER": "CONTO", "BIC": "BIC", "SSN": "ID", "IP_ADDRESS": "IP", "URL": "URL", "USERNAME": "UTENTE",
    "PASSWORD": "PASSWORD", "PIN": "PIN", "SECRET": "SEGRETO", "LICENSE_PLATE": "TARGA", "BARCODE": "CODICE",
    "SIGNATURE": "FIRMA", "STAMP": "TIMBRO", "FACE": "VOLTO", "CRYPTO_ADDRESS": "WALLET",
}


@dataclass(frozen=True)
class Run:
    """A stretch of text to hide on one line, in output pixels.

    ``x0, x1``: padded horizontal extent; ``y0, y1``: padded vertical band; ``glyph``: unpadded
    glyph height of the line (the bucket unit); ``label``: entity type ("" = none).
    """

    x0: int
    y0: int
    x1: int
    y1: int
    glyph: float
    label: str = ""


def label_for(entity_type: str) -> str:
    """Why: a type tag makes a cover read as "redacted" without saying anything of the content.
    What: the short label of an entity type, "" for unknown types. Test: PERSON -> NOME, FOO -> ""."""
    return LABELS.get(entity_type, "")


def bucket_width(needed: float, glyph: float) -> int:
    """Why: a cover as wide as its text tells the number of hidden characters.
    What: the smallest multiple of BUCKET x glyph that is >= ``needed``, plus a jitter in
    [0, JITTER x glyph) derived only from (bucket index, unit), so texts of different lengths in one
    bucket get exactly the same width and the jitter carries no information about them.
    Test: glyph 20 -> unit 35: needed 36 and 69 give the same width, >= 70; needed 71 gives more.
    """
    unit = max(1.0, BUCKET * glyph)
    k = max(1, math.ceil(needed / unit - 1e-9))
    seed = hashlib.blake2b(f"{k}:{round(unit)}".encode(), digest_size=2).digest()
    return math.ceil(k * unit + int.from_bytes(seed, "big") / 65536 * JITTER * glyph)


def same_lines(runs: Sequence[Run]) -> list[Run]:
    """Why: per-run heights would trace each word's ascenders/descenders; one height per line does not.
    What: groups runs whose band centres are within SAME_LINE x glyph of each other and gives every
    run of a group the group's union band and largest glyph height.
    Test: runs with bands (10, 30) and (12, 34) on one line -> both (10, 34)."""
    out: list[Run] = []
    groups: list[list[Run]] = []
    for run in sorted(runs, key=lambda r: (r.y0 + r.y1) / 2):
        centre = (run.y0 + run.y1) / 2
        last = groups[-1] if groups else None
        if (last and max(run.glyph, last[0].glyph) <= MAX_LINE_GLYPH_RATIO * max(1, min(run.glyph, last[0].glyph))
                and abs(centre - (last[0].y0 + last[0].y1) / 2) < SAME_LINE * max(run.glyph, last[0].glyph)):
            last.append(run)
        else:
            groups.append([run])
    for group in groups:
        y0, y1, glyph = min(r.y0 for r in group), max(r.y1 for r in group), max(r.glyph for r in group)
        out.extend(replace(r, y0=y0, y1=y1, glyph=glyph) for r in group)
    return out


def _merged(runs: list[Run], reach: float) -> list[Run]:
    """Runs of one line closer than ``reach`` become one cover (a label survives only if shared)."""
    out: list[Run] = []
    for run in sorted(runs, key=lambda r: r.x0):
        if out and run.x0 - out[-1].x1 <= reach:
            prev = out[-1]
            out[-1] = replace(prev, x1=max(prev.x1, run.x1), label=prev.label if prev.label == run.label else "")
        else:
            out.append(run)
    return out


def pill_boxes(runs: Sequence[Run], width: int, height: int,
               neighbours: Sequence[BBox] = ()) -> list[tuple[BBox, int, str, BBox]]:
    """Why: the founder's ID-card sample read as one black slab; covers must hug each line yet hide length.
    What: (box, radius, label, solid) per cover (``solid``: the padded run, always opaque): runs
    normalized per line, merged when their rounded ends would touch, widened by the radius on both
    ends where there is room (rounded caps lie outside the padded box) and to ``bucket_width``;
    the extra width goes first into free room to the right, then to the left (before visible
    ``neighbours`` words, if any), then evenly wherever the image allows.
    Test: a 100 px run at x 50 on a 20 px line -> box contains [50, 150] grown by the radius, width
    == bucket_width(...); a run touching the right edge grows leftwards.
    """
    out = []
    lines: dict[tuple[int, int], list[Run]] = {}
    normalized = same_lines(runs)
    for run in normalized:
        lines.setdefault((run.y0, run.y1), []).append(run)
    for (y0, y1), line in lines.items():
        radius = max(1, round(PILL_RADIUS * (y1 - y0)))
        glyph = max(r.glyph for r in line)
        others = sorted(b for b in neighbours if abs((b[1] + b[3]) / 2 - (y0 + y1) / 2) < SAME_LINE * glyph)
        for run in _merged(line, 2 * radius):
            barriers = [other for other in normalized if (other.y0, other.y1) != (y0, y1)
                        and other.y0 < y1 and other.y1 > y0
                        and max(other.glyph, glyph) > MAX_LINE_GLYPH_RATIO * max(1, min(other.glyph, glyph))]
            nearby = others + [(other.x0, other.y0, other.x1, other.y1) for other in barriers]
            gap = NEIGHBOUR_GAP * glyph
            middle = (run.x0 + run.x1) / 2
            right_edge = min((o[0] - gap for o in nearby if (o[0] + o[2]) / 2 > middle), default=width)
            left_edge = max((o[2] + gap for o in nearby if (o[0] + o[2]) / 2 < middle), default=0)
            # rounded caps sit outside the padded run, but never over a visible neighbour (square corner then)
            a = max(0, run.x0 - min(radius, max(0, int(run.x0 - left_edge))))
            b = min(width, run.x1 + min(radius, max(0, int(right_edge - run.x1))))
            extra = min(width, bucket_width(b - a, glyph)) - (b - a)
            if barriers:
                extra = min(extra, max(0, int(right_edge - b)) + max(0, int(a - left_edge)))
            grow_right = min(extra, max(0, int(right_edge - b)))
            grow_left = min(extra - grow_right, max(0, int(a - left_edge)))
            rest = extra - grow_right - grow_left  # no free room left: overflow evenly, within the image
            more_right = min(width - b - grow_right, rest - rest // 2)
            grow_left = min(a, grow_left + rest - more_right)
            more_right = min(width - b - grow_right, extra - grow_right - grow_left)
            out.append(((a - grow_left, y0, b + grow_right + more_right, y1), radius, run.label,
                        (run.x0, y0, run.x1, y1)))
    return out


def area_box(box: BBox, width: int, height: int) -> tuple[BBox, int]:
    """An area's cover: grown by half its corner radius (so the corners still contain ``box``), clipped."""
    x0, y0, x1, y1 = box
    radius = min(AREA_RADIUS_MAX, round(AREA_RADIUS * min(x1 - x0, y1 - y0)))
    grow = math.ceil(radius / 2)
    return (max(0, x0 - grow), max(0, y0 - grow), min(width, x1 + grow), min(height, y1 + grow)), radius


@lru_cache(maxsize=32)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size)


def draw_cover(image: Image.Image, box: BBox, radius: int, label: str = "", solid: BBox | None = None,
               show_label: bool = True) -> None:
    """Why: one renderer for every cover keeps the look and the opacity guarantee in one place.
    What: paints a rounded rectangle ``box`` (uniform opaque fill + subtle rim, anti-aliased corners)
    on RGB ``image``; every pixel of ``solid`` (default: the box shrunk by the corner cut) is forced
    fully opaque; ``label`` is drawn centred, small caps, only if it fits inside the straight part.
    Test: every pixel of ``solid`` differs from the original and is within the fill palette.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    radius = max(0, min(radius, w // 2, h // 2))
    big = Image.new("L", (w * SUPERSAMPLE, h * SUPERSAMPLE), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SUPERSAMPLE - 1, h * SUPERSAMPLE - 1),
                                          radius * SUPERSAMPLE, fill=255)
    alpha = np.asarray(big.resize((w, h), Image.Resampling.BOX), dtype=np.float32) / 255
    sx0, sy0, sx1, sy1 = solid if solid is not None else (x0 + radius // 3, y0, x1 - radius // 3, y1)
    alpha[max(0, sy0 - y0):max(0, sy1 - y0), max(0, sx0 - x0):max(0, sx1 - x0)] = 1.0  # opacity guarantee
    fill = np.empty((h, w, 3), dtype=np.float32)
    fill[:] = COVER_FILL
    inner = alpha >= 1.0
    padded = np.pad(inner, 1, constant_values=False)
    rim = inner & ~(padded[2:, 1:-1] & padded[:-2, 1:-1] & padded[1:-1, 2:] & padded[1:-1, :-2])
    if w > 6 and h > 6:
        fill[rim] = fill[rim] * (1 - RIM_MIX) + np.asarray(RIM, np.float32) * RIM_MIX
    region = np.asarray(image.crop(box), dtype=np.float32)
    mixed = fill * alpha[..., None] + region * (1 - alpha[..., None])
    tile = Image.fromarray(np.clip(mixed + 0.5, 0, 255).astype(np.uint8), "RGB")
    size = round(LABEL_SIZE * h)
    if show_label and label and size >= LABEL_MIN_PX:
        font = _font(size)
        text = label.upper()
        left, top, right, bottom = ImageDraw.Draw(tile).textbbox((0, 0), text, font=font)
        if right - left <= w - 2 * max(radius, size // 2) and bottom - top <= h - 4:
            ImageDraw.Draw(tile).text(((w - (right - left)) / 2 - left, (h - (bottom - top)) / 2 - top), text,
                                      font=font, fill=LABEL_INK)
    image.paste(tile, (x0, y0))


def paint_pills(image: Image.Image, runs: Sequence[Run], neighbours: Sequence[BBox] = (),
                show_labels: bool = True) -> None:
    """Text covers (see pill_boxes) painted on ``image``; each run's padded box is always fully opaque."""
    for box, radius, label, solid in pill_boxes(runs, image.width, image.height, neighbours):
        draw_cover(image, box, radius, label, solid, show_labels)


def paint_area(image: Image.Image, box: BBox, label: str = "", show_label: bool = True) -> None:
    """An area cover (uncertain region, visual hit, user area): ``box`` fully opaque, rounded outside it."""
    if box[2] > box[0] and box[3] > box[1]:
        grown, radius = area_box(box, image.width, image.height)
        draw_cover(image, grown, radius, label, box, show_label)


def _cover_mask(image: Image.Image, box: BBox) -> tuple[np.ndarray, np.ndarray]:
    x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
    x1, y1 = min(image.width, int(box[2])), min(image.height, int(box[3]))
    rgb = np.asarray(image.convert("RGB").crop((x0, y0, max(x0, x1), max(y0, y1))), dtype=np.int16)
    return rgb, rgb[..., 2] - np.maximum(rgb[..., 0], rgb[..., 1]) >= COVER_BLUE


def cover_share(image: Image.Image, box: BBox) -> float:
    """Why: tests and audits must tell "covered" from "dark" now that covers are not black.
    What: the share of ``box``'s pixels (clipped to the image; empty -> 1.0) that are cover fill:
    blue at least COVER_BLUE above both red and green (the indigo fill, edge and label all are;
    neutral ink, paper and white are not).
    Test: a box fully inside a paint_area cover -> 1.0; the same box on the untouched page -> 0.0."""
    _, cover = _cover_mask(image, box)
    return float(cover.mean()) if cover.size else 1.0


def visible_ink(image: Image.Image, box: BBox) -> float:
    """Why: a text cover hugs the glyphs, not the loose OCR box; what matters is that no ink shows.
    What: the share of ``box``'s pixels (clipped) that are dark (grey < 128) and not cover fill.
    Test: a redacted word's OCR box -> 0.0; the same box before redaction -> > 0."""
    rgb, cover = _cover_mask(image, box)
    if not cover.size:
        return 0.0
    grey = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return float(((grey < 128) & ~cover).mean())
