"""Pure-function tests: parsing, geometry, image analysis, pipeline policy."""
from __future__ import annotations

import time

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.engines import RawWord, remaining
from app.engines.tesseract import encode_pgm, parse_tsv
from app.errors import OcrError
from app.imageops import Transform, components, estimate_skew, ink_without_text, merge_boxes, otsu_threshold, rotate
from app.inputs import fit_scale, parse_pages
from app.pipeline import Attempt, build_lines
from app.schemas import Word
from synth import cer_wer, edit_distance, make_page

TSV = "\n".join([
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t",
    "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96.5\tMario",
    "5\t1\t1\t1\t1\t2\t45\t20\t30\t10\t91\tRossi",
    "5\t1\t1\t1\t2\t1\t10\t40\t30\t10\t-1\t ",
    "5\t1\t2\t1\t1\t1\t10\t60\t30\t10\t55\tTorino",
])


def test_parse_tsv_keeps_words_and_sequential_lines() -> None:
    words = parse_tsv(TSV)
    assert [(w.text, w.line, w.block) for w in words] == [("Mario", 0, 1), ("Rossi", 0, 1), ("Torino", 1, 2)]
    assert words[0].bbox == (10, 20, 40, 30) and words[0].conf == 96.5


def test_encode_pgm() -> None:
    assert encode_pgm(Image.new("L", (2, 1), 7)) == b"P5\n2 1\n255\n\x07\x07"


@pytest.mark.parametrize("spec,total,expected", [(None, 3, [0, 1, 2]), ("2-3", 5, [1, 2]), ("4", 5, [3]), (" 1 - 2 ", 2, [0, 1])])
def test_parse_pages(spec: str | None, total: int, expected: list[int]) -> None:
    assert parse_pages(spec, total, 10) == expected


@pytest.mark.parametrize("spec,total", [("4-2", 5), ("0", 5), ("6", 5), ("a", 5), (None, 30)])
def test_parse_pages_rejects(spec: str | None, total: int) -> None:
    with pytest.raises(OcrError):
        parse_pages(spec, total, 20)


def test_fit_scale() -> None:
    assert fit_scale(1000, 1000, 1.0, 250_000) == pytest.approx(0.4975)
    assert fit_scale(10, 10, 2.0, 250_000) == 2.0


def test_remaining_raises_after_deadline() -> None:
    with pytest.raises(OcrError) as error:
        remaining(time.monotonic() - 1)
    assert error.value.status == 504


def test_transform_maps_rotated_points_back() -> None:
    image = Image.new("L", (200, 100), 255)
    image.putpixel((30, 20), 0)
    rotated, transform = rotate(image, 7.0, Transform.identity(200, 100))
    ys, xs = np.nonzero(np.asarray(rotated) < 128)
    x, y = transform.point(float(xs.mean()) + 0.5, float(ys.mean()) + 0.5)
    assert abs(x - 30.5) < 1.5 and abs(y - 20.5) < 1.5
    assert Transform.identity(10, 10).box((1.2, 2.7, 3.1, 4.0)) == (1, 2, 4, 4)


def test_components_and_merge() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[0:2, 0:2] = True
    mask[5:7, 5:7] = True
    assert sorted(components(mask)) == [((0, 0, 2, 2), 4), ((5, 5, 7, 7), 4)]
    assert merge_boxes([(0, 0, 10, 10), (12, 0, 20, 10)], gap=3) == [(0, 0, 20, 10)]
    assert merge_boxes([(0, 0, 1, 1), (50, 50, 60, 60)]) == [(0, 0, 1, 1), (50, 50, 60, 60)]


def test_otsu_threshold_splits_bimodal() -> None:
    array = np.array([20] * 50 + [230] * 50, dtype=np.uint8)
    assert 20 <= otsu_threshold(array) < 230


def test_estimate_skew_recovers_rotation() -> None:
    page = make_page(dpi=150).image.rotate(-4, fillcolor=255)
    assert estimate_skew(page, 10) == pytest.approx(4.0, abs=0.3)
    assert estimate_skew(Image.new("L", (500, 500), 255), 10) == 0.0


def test_ink_without_text_finds_scribble_only() -> None:
    image = Image.new("L", (1000, 1000), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 400, 140), fill=0)  # "text"
    draw.line([(600, 700), (700, 760), (800, 690), (900, 750)], fill=0, width=6)  # "signature"
    regions = ink_without_text(image, [(95, 95, 405, 145)])
    assert len(regions) == 1
    x0, y0, x1, y1 = regions[0]
    assert x0 <= 600 and x1 >= 900 and y0 <= 690 and y1 >= 760
    assert ink_without_text(image, [(95, 95, 405, 145), (590, 680, 910, 770)]) == []


def test_build_lines_and_attempt_scoring() -> None:
    words = [Word(text="Mario", conf=90, bbox=(0, 0, 5, 5), line_id=0, block_id=0),
             Word(text="Rossi", conf=90, bbox=(6, 1, 12, 6), line_id=0, block_id=0)]
    (line,) = build_lines(words)
    assert line.text == "Mario Rossi" and line.bbox == (0, 0, 12, 6)
    attempt = Attempt("x", [RawWord("abcde", 80, (0, 0, 1, 1), 0, 0)] * 2)
    assert attempt.score == pytest.approx(8.0) and attempt.mean_conf == pytest.approx(80)
    assert Attempt("x", []).mean_conf == 0


def test_metrics() -> None:
    assert edit_distance("kitten", "sitting") == 3
    assert cer_wer("a b c", "a  b c") == (0.0, 0.0)
