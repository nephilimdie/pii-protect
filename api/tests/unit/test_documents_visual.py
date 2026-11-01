"""Visual PII (faces, QR/barcodes, plates) from the OCR service's /v1/visual-pii on images and
scanned PDF pages, plus the tilt-aware padding of OCR line boxes.

A fake service answers /v1/ocr with the known text layout and /v1/visual-pii with one face,
one QR code and one plate (scaled to the image it receives). Pixel sampling on the output
proves those regions are black; the preview proves the contract (visual_entities, types).
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.documents import ocr_client
from app.documents.ocr_client import OcrClient, VisualHit, parse_visual
from app.documents.models import SegmentEdit
from app.documents.ocr_layout import ScannedPage, paint, to_device
from app.routers import documents as documents_module
from tests.unit import test_documents as base
from tests.unit import test_documents_image as image_tests
from tests.unit import test_documents_ocr as scan_tests
from tests.unit.test_documents import _post, env  # noqa: F401  (fixture reuse)

FACE, QR, PLATE = (900, 80, 1100, 300), (60, 420, 260, 620), (700, 600, 1000, 680)  # in SCREENSHOT pixels
SCAN_FACE = (900, 100, 1150, 400)  # in SCAN_SIZE pixels (top-right photo on an ID scan)


class FakeVisual:
    """Routes /v1/visual-pii to known boxes (scaled), everything else to the OCR fake."""

    def __init__(self, ocr, boxes: list[tuple[str, tuple[int, int, int, int], bool]], frame: tuple[int, int]) -> None:
        self.ocr, self.boxes, self.frame, self.calls, self.fail, self.modes = ocr, boxes, frame, [], None, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v1/visual-pii":
            return self.ocr(request)
        body = request.content
        self.calls.append(body.split(b'name="detectors"\r\n\r\n', 1)[1].split(b"\r\n", 1)[0].decode())
        if self.fail:
            return httpx.Response(503, json={"error": "NOT_READY", "message": "face detector missing"})
        image = Image.open(io.BytesIO(body[body.index(b"\x89PNG"):]))
        self.modes.append(image.mode)
        f = image.width / self.frame[0]
        return httpx.Response(200, json={"width": image.width, "height": image.height, "boxes": [
            {"type": kind, "bbox": [min(round(v * f), image.width if i % 2 == 0 else image.height)
                                    for i, v in enumerate(box)], "score": 0.9, "needs_review": review}
            for kind, box, review in self.boxes]})


def _client(fake, monkeypatch, detectors: str = "face,code,plate") -> OcrClient:
    client = OcrClient("http://ocr:8090", "k", 30, 1, 10, visual_detectors=detectors,
                       transport=httpx.MockTransport(lambda r: fake(r)), sleep=lambda _: None)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    return client


@pytest.fixture
def vis(env, monkeypatch):  # noqa: F811
    env.fake = FakeVisual(image_tests.FakeOcr(image_tests.SCREENSHOT),
                          [("FACE", FACE, False), ("QR_CODE", QR, False), ("LICENSE_PLATE", PLATE, True)],
                          image_tests.SCREENSHOT.size)
    _client(env.fake, monkeypatch)
    monkeypatch.setitem(base._PATTERNS, image_tests.IBAN, "IBAN")
    monkeypatch.setitem(base._PATTERNS, image_tests.PHONE, "PHONE")
    return env


def _dark(image: Image.Image, box, f: float = 1.0) -> bool:
    return image_tests._mean(image, tuple(round(v * f) for v in box)) < 20


# ── units ────────────────────────────────────────────────────────────────────

def test_parse_visual_maps_qr_to_barcode_and_rejects_bad_answers():
    good = {"width": 100, "height": 50, "boxes": [{"type": "QR_CODE", "bbox": [1, 2, 30, 40], "score": 1.0,
                                                    "needs_review": False}]}
    assert parse_visual(good, 100, 50) == [VisualHit("BARCODE", (1, 2, 30, 40), 1.0, False)]
    for bad in ({**good, "width": 99}, {**good, "boxes": [{"type": "EYES", "bbox": [0, 0, 1, 1]}]},
                {**good, "boxes": [{"type": "FACE", "bbox": [0, 0, 101, 10]}]}, {**good, "boxes": [{"type": "FACE"}]}):
        with pytest.raises(ValueError):
            parse_visual(bad, 100, 50)


def test_tilt_pads_line_boxes_only_on_tilted_pages():
    line = (0, 100, 1000, 140)
    assert to_device(line, 1, 1, 2000, 2000, True) == (0, 94, 1006, 146)
    assert to_device(line, 1, 1, 2000, 2000, True, skew=0.3) == (0, 94, 1006, 146)  # straight enough
    assert to_device(line, 1, 1, 2000, 2000, True, skew=-3.0) == (0, 85, 1018, 155)  # +12 x, +9 y
    assert to_device(line, 1, 1, 2000, 2000, False, skew=3.0) == (0, 97, 1003, 143)  # regions: unchanged


def test_tilted_word_box_clipping_last_glyph_is_still_covered():
    """The 2a prod gap: a tilted photo whose OCR word box ended a few px before the last digit."""
    result = scan_tests._result([("4567", (100, 200, 300, 240), 0, 0)])
    page = ScannedPage.from_ocr(result.__class__(**{**result.__dict__, "skew": 2.5}))
    image = Image.new("RGB", (1000, 1000), "white")
    image.paste((0, 0, 0), (300, 204, 310, 238))  # ink of the last glyph just outside the word box
    paint(image, page, [SegmentEdit(0, 0, 4, "")], [])
    assert image.crop((296, 196, 314, 244)).convert("L").getextrema() == (0, 0)


# ── images ───────────────────────────────────────────────────────────────────

def test_image_redact_paints_face_code_and_plate(vis):
    r = _post(vis, "redact", image_tests.png(image_tests.SCREENSHOT.image))
    assert r.status_code == 200, r.text
    out = Image.open(io.BytesIO(r.content))
    image_tests._assert_redacted(out, image_tests.SCREENSHOT)
    assert all(_dark(out, box) for box in (FACE, QR, PLATE))
    assert {"BARCODE", "FACE", "LICENSE_PLATE"} <= set(r.headers["x-pii-types"].split(","))
    assert vis.fake.calls == ["face,code,plate"] and vis.fake.modes == ["RGB"]  # colour frame for faces


def test_image_preview_lists_visual_entities(vis):
    body = _post(vis, "preview", image_tests.png(image_tests.SCREENSHOT.image)).json()
    w, h = image_tests.SCREENSHOT.size
    assert [(v["id"], v["type"], v["page"], v["needs_review"]) for v in body["visual_entities"]] == [
        (0, "FACE", 1, False), (1, "BARCODE", 1, False), (2, "LICENSE_PLATE", 1, True)]
    assert body["visual_entities"][0]["bbox"] == pytest.approx([FACE[0] / w, FACE[1] / h, FACE[2] / w, FACE[3] / h],
                                                               abs=0.002)
    assert {"FACE", "BARCODE", "LICENSE_PLATE"} <= set(body["pii_types_found"])
    assert len(body["needs_review"]) == 2  # text review regions keep their ids (review_keep unchanged)


def test_photo_with_only_a_face_is_redacted_not_rejected(vis):
    vis.fake.ocr.layout = image_tests.Layout((300, 200), [], 20, "white", low=(0, 0, 0, 0), ink=(0, 0, 0, 0))
    vis.fake.ocr.layout.words = []
    vis.fake.frame, vis.fake.boxes = (300, 200), [("FACE", (100, 40, 200, 160), False)]
    r = _post(vis, "redact", image_tests.png(Image.new("RGB", (300, 200), (200, 180, 160))))
    assert r.status_code == 200, r.text
    assert _dark(Image.open(io.BytesIO(r.content)), (100, 40, 200, 160))


def test_visual_failure_fails_closed(vis):
    vis.fake.fail = True
    for op in ("redact", "preview"):
        r = _post(vis, op, image_tests.png(image_tests.SCREENSHOT.image))
        assert r.status_code == 503 and r.json()["error"] == "OCR_UNAVAILABLE", r.text
        assert b"PNG" not in r.content


def test_visual_disabled_makes_no_call(vis, monkeypatch):
    _client(vis.fake, monkeypatch, detectors="")
    body = _post(vis, "preview", image_tests.png(image_tests.SCREENSHOT.image)).json()
    assert body["visual_entities"] == [] and vis.fake.calls == []


def test_visual_pii_setting_builds_the_client(monkeypatch):
    monkeypatch.setattr(settings, "ocr_enabled", True)
    for enabled, expected in ((False, ""), (True, "face,code,plate")):
        monkeypatch.setattr(settings, "visual_pii_enabled", enabled)
        ocr_client.get_ocr_client.cache_clear()
        assert ocr_client.get_ocr_client().visual_detectors == expected
    ocr_client.get_ocr_client.cache_clear()


# ── scanned PDF pages ────────────────────────────────────────────────────────

def test_scanned_pdf_page_face_is_painted(env, monkeypatch):  # noqa: F811
    env.fake = FakeVisual(scan_tests.FakeOcr(), [("FACE", SCAN_FACE, True)], scan_tests.SCAN_SIZE)
    _client(env.fake, monkeypatch, detectors="face,code")
    monkeypatch.setitem(base._PATTERNS, scan_tests.IBAN, "IBAN")
    r = _post(env, "redact", scan_tests.make_scan_pdf(pages=2), domain="hr_payroll")
    assert r.status_code == 200, r.text
    pages = scan_tests._pages(r.content)
    for _, _, image in pages:
        scan_tests._assert_scan_redacted(image)
        assert scan_tests._mean(image, SCAN_FACE) < 20
    assert env.fake.calls == ["face,code", "face,code"] and "FACE" in r.headers["x-pii-types"]


# ── real OCR service (CI starts the container) ───────────────────────────────

MONA = Path(__file__).parents[3] / "ocr-service" / "tests" / "fixtures" / "mona_lisa_330.jpg"  # public domain


@pytest.mark.skipif(not image_tests.REAL_URL or not MONA.is_file(), reason="needs PII_OCR_TEST_URL + the PD fixture")
def test_real_visual_pii_face_and_text_on_one_photo(env, monkeypatch):  # noqa: F811
    client = OcrClient(image_tests.REAL_URL, os.environ.get("PII_OCR_TEST_KEY", "ci-key"), 120, 3, 10,
                       visual_detectors="face,code,plate")
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    scene = image_tests.SCREENSHOT.image.copy()
    face_at = (980, 300)
    scene.paste(Image.open(MONA).convert("RGB").resize((165, 246)), face_at)
    body = _post(env, "preview", image_tests.png(scene)).json()
    faces = [v for v in body["visual_entities"] if v["type"] == "FACE"]
    assert len(faces) == 1 and "FACE" in body["pii_types_found"], body["visual_entities"]
    out = Image.open(io.BytesIO(_post(env, "redact", image_tests.png(scene)).content)).convert("RGB")
    eyes_to_chin = (face_at[0] + 62, face_at[1] + 45, face_at[0] + 95, face_at[1] + 85)  # fixture face at half scale
    assert _dark(out, eyes_to_chin)
