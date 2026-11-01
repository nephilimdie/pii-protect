"""Synthetic Italian document pages with exact ground-truth word boxes (tests + benchmark)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)

PARAGRAPHS = (
    "Spettabile Società Edile Rossi S.r.l., con la presente si comunica che il sig. Mario Bianchi,",
    "nato a Torino il 12/03/1978, codice fiscale BNCMRA78C12L219K, residente in via Garibaldi 45,",
    "10122 Torino, ha richiesto il rimborso della fattura n. 2024/118 di euro 1.250,00.",
    "Il pagamento sarà effettuato sul conto IBAN IT60X0542811101000000123456 entro trenta giorni.",
    "Per qualsiasi chiarimento è possibile contattare l'ufficio al numero 011 5551234 oppure",
    "scrivere all'indirizzo amministrazione@rossiedile.it indicando il numero di pratica.",
    "La dott.ssa Giulia Esposito, responsabile del procedimento, verificherà la documentazione",
    "entro il 30 novembre; perché la richiesta sia accolta occorre allegare copia del documento.",
    "Distinti saluti. Questo documento è stato generato per verificare il riconoscimento ottico.",
)


@dataclass(frozen=True)
class SynthPage:
    """Why: OCR accuracy needs exact truth. What: image + list of (word, box) + full text.
    Test: ``make_page().words`` is non-empty and every box lies inside the image.
    """

    image: Image.Image
    words: list[tuple[str, tuple[int, int, int, int]]]

    @property
    def text(self) -> str:
        """Why/What: reference text for CER/WER (single spaces). Test: contains "Bianchi"."""
        return " ".join(w for w, _ in self.words)


def font(size: int) -> ImageFont.FreeTypeFont:
    """Why: CI and macOS ship different fonts. What: first available TrueType font. Test: returns a font."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError("no TrueType font found; install fonts-dejavu-core")


def make_page(dpi: int = 300, lines: int = 9, scribble: bool = False) -> SynthPage:
    """Why: A4 business letter at ``dpi`` with 11 pt text, the typical engine input.
    What: renders PARAGRAPHS word by word (true boxes from the font metrics), optional
    handwritten-like scribble (a signature) bottom right.
    Test: at 300 DPI the image is 2480x3508.
    """
    width, height = round(8.27 * dpi), round(11.69 * dpi)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    face = font(round(11 / 72 * dpi))
    margin, y = round(dpi * 0.8), round(dpi * 1.0)
    space = draw.textlength(" ", font=face)
    words: list[tuple[str, tuple[int, int, int, int]]] = []
    for text in PARAGRAPHS[:lines]:
        x = float(margin)
        for word in text.split():
            draw.text((x, y), word, font=face, fill=0)
            box = draw.textbbox((x, y), word, font=face)
            words.append((word, (int(box[0]), int(box[1]), int(box[2]), int(box[3]))))
            x += draw.textlength(word, font=face) + space
        y += round(face.size * 1.6)
    if scribble:
        rng = random.Random(7)
        cx, cy = width - margin - dpi, y + dpi
        points = [(cx + i * dpi / 40, cy + rng.uniform(-1, 1) * dpi / 8) for i in range(40)]
        draw.line(points, fill=0, width=max(2, dpi // 60))
    return SynthPage(image, words)


def degrade(image: Image.Image, seed: int = 3, noise: float = 25.0, blur: float = 0.8) -> Image.Image:
    """Why: scans/photocopies are noisy. What: Gaussian blur + Gaussian noise + slight grey
    paper. Test: the result has the same size and a lower mean than the clean page.
    """
    rng = np.random.default_rng(seed)
    array = np.asarray(image.filter(ImageFilter.GaussianBlur(blur)), dtype=np.float32) * 0.92
    array += rng.normal(0, noise, array.shape)
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Why: word-box accuracy metric. What: intersection over union. Test: identical -> 1.0."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def edit_distance(a: list[str] | str, b: list[str] | str) -> int:
    """Why: CER (chars) and WER (tokens) share Levenshtein. What: O(len(a)*len(b)) DP.
    Test: ("kitten", "sitting") -> 3.
    """
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def cer_wer(reference: str, hypothesis: str) -> tuple[float, float]:
    """Why: standard OCR quality metrics. What: (CER, WER) on whitespace-normalised text.
    Test: identical strings -> (0.0, 0.0).
    """
    ref, hyp = " ".join(reference.split()), " ".join(hypothesis.split())
    return edit_distance(ref, hyp) / max(1, len(ref)), edit_distance(ref.split(), hyp.split()) / max(1, len(ref.split()))


def match_rate(truth: list[tuple[str, tuple[int, int, int, int]]], boxes: list[tuple[int, int, int, int]], threshold: float = 0.5) -> float:
    """Why: tests assert that most true words are covered by some predicted box.
    What: share of truth boxes with best IoU >= threshold. Test: identical lists -> 1.0.
    """
    hits = sum(1 for _, t in truth if max((iou(t, b) for b in boxes), default=0.0) >= threshold)
    return hits / max(1, len(truth))
