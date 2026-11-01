"""Real-engine accuracy on synthetic Italian pages (skipped without models unless OCR_REQUIRE_MODELS=1)."""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings, pdf, png, post
from synth import cer_wer, degrade, iou, make_page, match_rate

PAGE = make_page(scribble=True)
SIGNATURE_AREA = (1800, 1150, 2300, 1400)


def ocr(client: TestClient, data: bytes, **fields: str) -> dict:  # type: ignore[type-arg]
    response = post(client, data, **fields)
    assert response.status_code == 200, response.text
    return response.json()["pages"][0]  # type: ignore[no-any-return]


def text_of(result: dict) -> str:  # type: ignore[type-arg]
    return " ".join(w["text"] for w in result["words"])


def boxes(result: dict) -> list[tuple[int, int, int, int]]:  # type: ignore[type-arg]
    return [tuple(w["bbox"]) for w in result["words"]]  # type: ignore[misc]


def covered(truth: tuple[int, int, int, int], predicted: list[tuple[int, int, int, int]], share: float = 0.8) -> bool:
    """A truth box is covered when >= ``share`` of its area lies inside one predicted box."""
    area = (truth[2] - truth[0]) * (truth[3] - truth[1])
    for b in predicted:
        ix = max(0, min(truth[2], b[2]) - max(truth[0], b[0]))
        iy = max(0, min(truth[3], b[3]) - max(truth[1], b[1]))
        if ix * iy >= share * area:
            return True
    return False


def test_tesseract_clean_page_word_boxes(real_client: TestClient) -> None:
    result = ocr(real_client, png(PAGE.image, dpi=(300, 300)), engine="tesseract")
    cer, wer = cer_wer(PAGE.text, text_of(result))
    assert result["engine"] == "tesseract" and (result["width"], result["height"]) == PAGE.image.size
    assert match_rate(PAGE.words, boxes(result), 0.6) >= 0.97
    assert cer <= 0.01 and wer <= 0.03
    assert any(w["text"].startswith("BNCMRA78C12L219K") for w in result["words"])
    assert any(w["text"].startswith("IT60X0542811101000000123456") for w in result["words"])


def test_tesseract_via_pdf_matches_image_frame(real_client: TestClient) -> None:
    result = ocr(real_client, pdf(PAGE.image, resolution=300.0), engine="tesseract")
    assert result["dpi"] == 300 and match_rate(PAGE.words, boxes(result), 0.6) >= 0.97


def test_noisy_page_stays_accurate(real_client: TestClient) -> None:
    result = ocr(real_client, png(degrade(PAGE.image)), engine="tesseract")
    cer, _ = cer_wer(PAGE.text, text_of(result))
    assert cer <= 0.03 and match_rate(PAGE.words, boxes(result), 0.5) >= 0.9


def test_rotated_page_is_deskewed_and_boxes_cover_the_words(real_client: TestClient) -> None:
    angle = -3.0  # Pillow: negative = clockwise
    rotated = PAGE.image.rotate(angle, resample=3, fillcolor=255)
    result = ocr(real_client, png(rotated), engine="tesseract")
    cer, _ = cer_wer(PAGE.text, text_of(result))
    assert cer <= 0.03
    cx, cy = rotated.width / 2, rotated.height / 2
    rad = math.radians(angle)
    hits = 0
    for _, (x0, y0, x1, y1) in PAGE.words:  # rotated word centres must fall inside a reported box
        mx, my = (x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy
        px, py = cx + mx * math.cos(rad) + my * math.sin(rad), cy - mx * math.sin(rad) + my * math.cos(rad)
        hits += any(b[0] <= px <= b[2] and b[1] <= py <= b[3] for b in boxes(result))
    assert hits / len(PAGE.words) >= 0.95


def test_rapidocr_boxes_cover_words(real_client: TestClient) -> None:
    result = ocr(real_client, png(PAGE.image), engine="rapidocr")
    predicted = boxes(result)
    assert result["engine"] == "rapidocr"
    assert sum(covered(t, predicted) for _, t in PAGE.words) / len(PAGE.words) >= 0.9
    assert cer_wer(PAGE.text, text_of(result))[0] <= 0.05  # PP-OCR alphabet lacks some Italian accents


def test_signature_is_reported_as_unreadable_or_low_confidence(real_client: TestClient) -> None:
    # Known limitation: RapidOCR's detector can read a scribble as a "word" (e.g. "wwwn", conf ~64),
    # so only tesseract/auto (the engine default) are guaranteed to surface it. See README.
    for engine in ("tesseract", "auto"):
        result = ocr(real_client, png(PAGE.image), engine=engine)
        regions = result["ink_without_text_regions"] + result["low_conf_regions"]
        assert any(iou(tuple(r), SIGNATURE_AREA) > 0.05 for r in regions), (engine, regions)  # type: ignore[arg-type]


def test_blank_page_has_no_words_or_regions(real_client: TestClient) -> None:
    result = ocr(real_client, png(PAGE.image.point(lambda _: 255)), engine="auto")
    assert result["words"] == [] and result["ink_without_text_regions"] == [] and result["low_conf_regions"] == []


def test_real_tesseract_timeout_kills_and_fails_closed(real_engines: dict[str, object]) -> None:
    with TestClient(create_app(make_settings(timeout_seconds=0.2), real_engines)) as c:  # type: ignore[arg-type]
        response = post(c, png(PAGE.image), engine="tesseract")
    assert response.status_code == 504 and response.json()["error"] == "OCR_TIMEOUT"


@pytest.mark.parametrize("turn", [90, 180, 270])
def test_sideways_page_is_turned_upright_by_osd(real_client: TestClient, turn: int) -> None:
    """No EXIF, no PDF /Rotate: OSD finds the turn, text reads and boxes map back to the sent frame."""
    turned = PAGE.image.rotate(turn, expand=True)  # Pillow: counter-clockwise
    result = ocr(real_client, png(turned), engine="tesseract")
    cer, _ = cer_wer(PAGE.text, text_of(result))
    assert cer <= 0.03, turn
    w, h = PAGE.image.size

    def to_turned(x: float, y: float) -> tuple[float, float]:
        return {90: (y, w - x), 180: (w - x, h - y), 270: (h - y, x)}[turn]

    hits = 0
    for _, (x0, y0, x1, y1) in PAGE.words:
        px, py = to_turned((x0 + x1) / 2, (y0 + y1) / 2)
        hits += any(b[0] <= px <= b[2] and b[1] <= py <= b[3] for b in boxes(result))
    assert hits / len(PAGE.words) >= 0.95, turn
