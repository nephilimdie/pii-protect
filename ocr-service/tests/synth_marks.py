"""Procedural signatures, stamps and forms with exact truth boxes (own work, no third-party images).

Signatures: chained cubic Bezier strokes with pressure (stroke width) variation, a slant and an
optional underline flourish. Stamps: Pillow rings + text (round/oval) or frames (rectangular)
in red/blue/violet ink, slightly faded. Forms: printed text, a table grid, a logo (filled shapes
+ bold text), labels ("Firma del dichiarante", "Timbro"), and the marks placed near them.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from synth import font

INKS = {"blue": (30, 50, 160), "black": (25, 25, 30), "red": (200, 30, 40), "violet": (110, 40, 150)}
Box = tuple[int, int, int, int]


@dataclass
class Form:
    """Why: precision/recall need truth. What: page image + true SIGNATURE / STAMP boxes.
    Test: ``make_form(seed=1).truth`` lists the marks that were drawn.
    """

    image: Image.Image
    truth: list[tuple[str, Box]] = field(default_factory=list)


def _bezier(p0, p1, p2, p3, steps: int):  # type: ignore[no-untyped-def]
    for i in range(steps + 1):
        t = i / steps
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        yield (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]), t


def draw_signature(draw: ImageDraw.ImageDraw, box: Box, rng: random.Random, ink: tuple[int, int, int],
                   pen: float) -> Box:
    """Why: signatures are handwriting: connected curvy strokes, pressure-varying width, slant.
    What: 2-3 pen-down strokes of 4-8 chained Bezier segments looping inside ``box``, plus an
    optional underline; returns the tight box of the drawn ink. Test: the box lies inside ``box``.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    slant = rng.uniform(0.1, 0.35)
    xs, ys = [], []
    strokes = rng.randint(2, 3)
    for k in range(strokes):
        left = x0 + w * k / strokes
        span = w / strokes * rng.uniform(1.0, 1.2)
        pts = [(left, y0 + h * rng.uniform(0.3, 0.8))]
        segments = rng.randint(4, 8)
        for s in range(segments):
            px = left + span * (s + 1) / segments
            pts += [(px - span / segments * rng.uniform(0.2, 1.4), y0 + h * rng.uniform(0.0, 1.0)),
                    (px + span / segments * rng.uniform(-0.6, 0.6), y0 + h * rng.uniform(0.0, 1.0)),
                    (px, y0 + h * rng.uniform(0.25, 0.85))]
        for s in range(segments):
            p0, p1, p2, p3 = pts[3 * s: 3 * s + 4]
            for (px, py), t in _bezier(p0, p1, p2, p3, 40):
                pressure = 0.45 + 0.55 * math.sin(math.pi * (s + t) / segments) * rng.uniform(0.85, 1.0)
                radius = max(0.6, pen * pressure / 2)
                qx = px + (y1 - py) * slant * 0.3
                qx, py = min(max(qx, x0 + radius), x1 - radius), min(max(py, y0 + radius), y1 - radius)
                draw.ellipse((qx - radius, py - radius, qx + radius, py + radius), fill=ink)
                xs += [qx - radius, qx + radius]
                ys += [py - radius, py + radius]
    if rng.random() < 0.5:  # underline flourish
        uy = y1 - h * 0.08
        for (px, py), t in _bezier((x0 + w * 0.1, uy), (x0 + w * 0.4, uy + h * 0.06), (x0 + w * 0.7, uy - h * 0.06),
                                   (x1 - w * 0.05, uy - h * 0.02), 120):
            radius = max(0.6, pen * (0.9 - 0.6 * t) / 2)
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=ink)
            xs += [px - radius, px + radius]
            ys += [py - radius, py + radius]
    return int(min(xs)), int(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))


def draw_stamp(image: Image.Image, center: tuple[int, int], size: int, ink: tuple[int, int, int],
               kind: str, rng: random.Random, text: str = "COMUNE DI ESEMPIO") -> Box:
    """Why: office stamps are rings/ovals or frames of coloured ink with text, often faded.
    What: draws a round/oval (double ring + text around + centre text) or rectangular (double
    frame + 2 text lines) stamp on an RGBA layer, fades it (random speckle loss, ~80% opacity)
    and composites it rotated by -15..15 deg; returns its box. Test: the box contains ``center``.
    """
    w = size if kind != "oval" else int(size * 1.45)
    h = size if kind != "rect" else int(size * 0.55)
    if kind == "rect":
        w = int(size * 1.5)
    layer = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    line = max(2, size // 45)
    face = font(max(8, size // 11))
    if kind in ("round", "oval"):
        d.ellipse((4, 4, w + 3, h + 3), outline=ink + (255,), width=line)
        d.ellipse((4 + size // 10, 4 + size // 10, w + 3 - size // 10, h + 3 - size // 10), outline=ink + (255,), width=max(1, line // 2))
        cx, cy = (w + 8) / 2, (h + 8) / 2
        rx, ry = (w / 2) - size * 0.05 - 2, (h / 2) - size * 0.05 - 2
        for i, ch in enumerate(text):
            a = -math.pi * 0.95 + i * (1.9 * math.pi / max(1, len(text) - 1)) * 0.5
            glyph = Image.new("RGBA", (face.size * 2, face.size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(glyph).text((face.size // 2, face.size // 2), ch, font=face, fill=ink + (255,))
            glyph = glyph.rotate(-math.degrees(a) - 90, resample=Image.Resampling.BICUBIC)
            px, py = cx + rx * 0.82 * math.cos(a), cy + ry * 0.82 * math.sin(a)
            layer.alpha_composite(glyph, (int(px - glyph.width / 2), int(py - glyph.height / 2)))
        d.text((cx, cy), "N. 42", font=face, fill=ink + (255,), anchor="mm")
    else:
        d.rectangle((4, 4, w + 3, h + 3), outline=ink + (255,), width=line)
        d.rectangle((4 + line * 3, 4 + line * 3, w + 3 - line * 3, h + 3 - line * 3), outline=ink + (255,), width=max(1, line // 2))
        d.text(((w + 8) / 2, (h + 8) * 0.38), text[:16], font=face, fill=ink + (255,), anchor="mm")
        d.text(((w + 8) / 2, (h + 8) * 0.66), "PROT. 2026/118", font=face, fill=ink + (255,), anchor="mm")
    alpha = np.asarray(layer.getchannel("A"), dtype=np.float32)
    keep = np.random.default_rng(rng.randint(0, 10 ** 6)).random(alpha.shape) > 0.12  # worn ink
    layer.putalpha(Image.fromarray((alpha * keep * rng.uniform(0.7, 0.9)).astype(np.uint8)))
    layer = layer.rotate(rng.uniform(-15, 15), resample=Image.Resampling.BICUBIC, expand=True)
    left, top = center[0] - layer.width // 2, center[1] - layer.height // 2
    image.alpha_composite(layer, (left, top)) if image.mode == "RGBA" else image.paste(layer, (left, top), layer)
    bbox = layer.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox() or (0, 0, layer.width, layer.height)
    return left + bbox[0], top + bbox[1], left + bbox[2], top + bbox[3]


def draw_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, colour: tuple[int, int, int]) -> None:
    """A company logo: filled disc + filled square + bold-ish name (must NOT be a mark)."""
    draw.ellipse((x, y, x + size, y + size), fill=colour)
    draw.rectangle((x + size * 0.6, y + size * 0.6, x + size * 1.3, y + size * 1.3), fill=(40, 40, 40))
    draw.text((x + size * 1.5, y + size * 0.2), "ACME Edile S.r.l.", font=font(int(size * 0.55)), fill=colour,
              stroke_width=1, stroke_fill=colour)


def make_form(seed: int = 0, dpi: int = 200, signature: bool = True, stamp: str | None = "round",
              stamp_ink: str = "red", sig_ink: str = "blue", label: bool = True, colour_page: bool = True) -> Form:
    """Why: a realistic A4 form: header logo, printed paragraphs (with PII), a table grid,
    labels at the bottom and the marks near them. What: RGB page + truth; ``stamp`` is
    round/oval/rect/None. Test: ``make_form(stamp=None, signature=False).truth == []``.
    """
    rng = random.Random(seed)
    width, height = round(8.27 * dpi), round(11.69 * dpi)
    image = Image.new("RGB", (width, height), (252, 251, 247))
    draw = ImageDraw.Draw(image)
    mm = dpi / 25.4
    text = font(round(11 / 72 * dpi))
    draw_logo(draw, int(20 * mm), int(15 * mm), int(14 * mm), (20, 70, 160) if colour_page else (30, 30, 30))
    y = 40 * mm
    lines = ["Il sottoscritto Mario Bianchi, nato a Torino il 12/03/1978, codice fiscale BNCMRA78C12L219K,",
             "residente in via Garibaldi 45, 10122 Torino, telefono 011 5551234, chiede il rimborso",
             "della fattura n. 2024/118 sul conto IBAN IT60X0542811101000000123456.",
             "Dichiara inoltre di aver preso visione dell'informativa sul trattamento dei dati personali."]
    for line in lines:
        draw.text((20 * mm, y), line, font=text, fill=(20, 20, 20))
        y += 7 * mm
    y += 6 * mm  # table: 4 columns x 5 rows
    cols, rows, cw, rh = 4, 5, 42 * mm, 8 * mm
    for r in range(rows + 1):
        draw.line((20 * mm, y + r * rh, 20 * mm + cols * cw, y + r * rh), fill=(30, 30, 30), width=max(1, dpi // 150))
    for c in range(cols + 1):
        draw.line((20 * mm + c * cw, y, 20 * mm + c * cw, y + rows * rh), fill=(30, 30, 30), width=max(1, dpi // 150))
    cells = (("Voce", "Quantità", "Prezzo", "Totale"), ("Cemento", "12", "8,50", "102,00"),
             ("Sabbia", "4", "21,00", "84,00"), ("Mattoni", "300", "0,45", "135,00"), ("", "", "IVA", "70,62"))
    for r, row in enumerate(cells):
        for c, value in enumerate(row):
            draw.text((20 * mm + c * cw + 2 * mm, y + r * rh + 1.5 * mm), value, font=text, fill=(20, 20, 20))
    form = Form(image)
    base = y + rows * rh + 30 * mm
    if label:
        draw.text((25 * mm, base), "Luogo e data: Torino, 14/04/2026", font=text, fill=(20, 20, 20))
        draw.text((120 * mm, base), "Firma del dichiarante", font=text, fill=(20, 20, 20))
        draw.line((115 * mm, base + 30 * mm, 185 * mm, base + 30 * mm), fill=(30, 30, 30), width=max(1, dpi // 150))
        draw.text((30 * mm, base + 40 * mm), "Timbro dell'ufficio", font=text, fill=(20, 20, 20))
    if signature:
        sw, sh = rng.uniform(40, 60) * mm, rng.uniform(12, 20) * mm
        sx, sy = 120 * mm + rng.uniform(0, 10) * mm, base + 8 * mm
        tight = draw_signature(draw, (int(sx), int(sy), int(sx + sw), int(sy + sh)), rng, INKS[sig_ink],
                               rng.uniform(0.4, 0.8) * mm)
        form.truth.append(("SIGNATURE", tight))
    if stamp:
        size = int(rng.uniform(28, 38) * mm)
        box = draw_stamp(image, (int(55 * mm), int(base + 75 * mm)), size, INKS[stamp_ink], stamp, rng)
        form.truth.append(("STAMP", box))
    return form


def scan(image: Image.Image, seed: int = 0, gray: bool = False, noise: float = 6.0) -> Image.Image:
    """A scanner/photocopier look: slight blur, noise, optional greyscale."""
    rng = np.random.default_rng(seed)
    out = image.filter(ImageFilter.GaussianBlur(0.6))
    array = np.asarray(out.convert("L") if gray else out, dtype=np.float32)
    array = np.clip(array + rng.normal(0, noise, array.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(array)
