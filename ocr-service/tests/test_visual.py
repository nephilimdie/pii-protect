"""POST /v1/visual-pii: faces (YuNet), QR/barcodes (zxing-cpp), Italian plates (OCR + regex).

Fixtures: a public-domain painting (tests/fixtures/README.md), codes generated with segno /
python-barcode, plates rendered with a system font. No photo of a real living person is used.
"""
from __future__ import annotations

import io
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.detectors import Hit, grow, iou, nms
from app.detectors.plates import find_plates
from app.engines import RawWord
from app.errors import OcrError
from app.main import build_detectors, create_app
from app.visual import parse_detectors
from conftest import AUTH, FakeEngine, make_settings, pdf, png, post
from synth import font

FIXTURES = Path(__file__).parent / "fixtures"


def visual(client: TestClient, data: bytes, headers: dict[str, str] | None = None, **fields: str):  # type: ignore[no-untyped-def]
    return client.post("/v1/visual-pii", headers=AUTH if headers is None else headers,
                       files={"file": ("img.png", data, "application/octet-stream")}, data=fields)


def contains(outer: list[int] | tuple[int, ...], inner: tuple[int, int, int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def mona() -> Image.Image:
    return Image.open(FIXTURES / "mona_lisa_330.jpg").convert("RGB")


def qr_image(text: str = "https://example.invalid/ticket/ABC123", scale: int = 6, border: int = 0) -> Image.Image:
    import segno

    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="png", scale=scale, border=border)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def barcode_image() -> Image.Image:
    import barcode
    from barcode.writer import ImageWriter

    buffer = io.BytesIO()
    barcode.get("code128", "PSEUDORA-0042", writer=ImageWriter()).write(
        buffer, {"write_text": False, "module_height": 15.0, "quiet_zone": 2.0})
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def plate_image(text: str = "AB 123 CD") -> tuple[Image.Image, tuple[int, int, int, int]]:
    """A car-ish scene: grey body, white plate with black text; returns the plate rectangle."""
    image = Image.new("RGB", (1200, 800), (90, 100, 110))
    draw = ImageDraw.Draw(image)
    plate = (420, 520, 820, 610)
    draw.rectangle(plate, fill="white", outline="black", width=3)
    draw.text((450, 530), text, fill="black", font=font(64))
    return image, plate


# --- units -------------------------------------------------------------------------------------

def test_parse_detectors_default_order_and_validation() -> None:
    assert parse_detectors(None) == ("face", "code", "plate")
    assert parse_detectors("plate, face") == ("face", "plate")
    for bad in ("face,eyes", ",", "FACE"):
        with pytest.raises(OcrError) as caught:
            parse_detectors(bad)
        assert caught.value.code == "INVALID_PARAMETER"


def test_nms_keeps_best_box() -> None:
    hits = [Hit("FACE", (0, 0, 10, 10), 0.9, False), Hit("FACE", (1, 1, 10, 10), 0.7, True),
            Hit("FACE", (50, 50, 60, 60), 0.8, False)]
    kept = nms(hits)
    assert len(kept) == 2 and kept[0].score == 0.9 and kept[0].needs_review is False
    assert iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0 and iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
    assert grow((10, 10, 20, 20), 0.1, 0.1, 100, 100) == (9, 9, 21, 21)


@pytest.mark.parametrize(("words", "review"), [
    (["AB", "123", "CD"], False),            # current format, spaced
    (["targa", "EF456GH"], False),           # inside a line of text
    (["AB", "12345"], True),                 # motorcycle: more false positives -> reviewed
    (["MI", "123456"], True),                # pre-1994 provincial
    (["ROMA", "A12345"], True),
])
def test_plate_formats(words: list[str], review: bool) -> None:
    raw = [RawWord(w, 95.0, (i * 100.0, 10.0, i * 100.0 + 90, 40.0), 0, 0) for i, w in enumerate(words)]
    (hit,) = find_plates(raw, review_conf=80.0)
    assert hit.type == "LICENSE_PLATE" and hit.needs_review is review
    first = 1 if words[0] == "targa" else 0
    assert hit.bbox == (first * 100.0, 10.0, (len(words) - 1) * 100.0 + 90, 40.0)


@pytest.mark.parametrize("text", ["IBAN IT60X0542811101000001234567", "CAP 00100", "MI 12AB34", "AB123CDE", "QO123IU"])
def test_plate_rejects_non_plates(text: str) -> None:
    raw = [RawWord(w, 95.0, (i * 100.0, 0.0, i * 100.0 + 90, 30.0), 0, 0) for i, w in enumerate(text.split())]
    assert find_plates(raw, review_conf=80.0) == []


def test_low_confidence_plate_is_reviewed() -> None:
    (hit,) = find_plates([RawWord("AB123CD", 55.0, (0, 0, 90, 30), 0, 0)], review_conf=80.0)
    assert hit.needs_review and hit.score == 0.55


# --- API contract (fake detectors) -------------------------------------------------------------

class FakeDetector:
    def __init__(self, hits: list[Hit]) -> None:
        self.hits, self.calls = hits, 0

    def detect(self, image: Image.Image) -> list[Hit]:
        self.calls += 1
        return self.hits

    def ready(self) -> dict[str, object]:
        return {"ok": True}


@pytest.fixture
def vclient() -> Iterator[TestClient]:
    detectors = {"face": FakeDetector([Hit("FACE", (10.2, 10.0, 50.0, 60.7), 0.91, False)]),
                 "code": FakeDetector([Hit("QR_CODE", (100, 100, 150, 150), 1.0, False)])}
    with TestClient(create_app(make_settings(), {"tesseract": FakeEngine()}, detectors)) as test_client:
        yield test_client


def test_visual_contract_shape(vclient: TestClient) -> None:
    response = visual(vclient, png(Image.new("RGB", (400, 300), "white")), detectors="face,code")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"width": 400, "height": 300, "boxes": [
        {"type": "FACE", "bbox": [10, 10, 50, 61], "score": 0.91, "needs_review": False},
        {"type": "QR_CODE", "bbox": [100, 100, 150, 150], "score": 1.0, "needs_review": False}]}


def test_visual_requires_key_and_valid_params(vclient: TestClient) -> None:
    data = png(Image.new("RGB", (64, 64), "white"))
    assert visual(vclient, data, headers={}).json()["error"] == "UNAUTHORIZED"
    assert visual(vclient, data, detectors="eyes").json()["error"] == "INVALID_PARAMETER"
    assert visual(vclient, data, page="0").json()["error"] == "INVALID_PARAMETER"
    assert visual(vclient, b"not an image").json()["error"] == "UNSUPPORTED_MEDIA_TYPE"


def test_visual_missing_detector_fails_closed(vclient: TestClient) -> None:
    """plate needs the rapidocr engine, absent here: 503 NOT_READY, never an empty answer."""
    response = visual(vclient, png(Image.new("RGB", (64, 64), "white")), detectors="plate")
    assert response.status_code == 503 and response.json()["error"] == "NOT_READY"


def test_visual_pdf_page_and_downscaled_frame(vclient: TestClient) -> None:
    two = pdf(Image.new("RGB", (850, 1100), "white"), Image.new("RGB", (850, 1100), "white"), resolution=100)
    body = visual(vclient, two, page="2", detectors="face").json()
    assert body["width"] == 2550 and abs(body["height"] - 3300) <= 1  # rendered at default_dpi 300
    assert visual(vclient, two, page="3").json()["error"] == "INVALID_PARAMETER"


# --- real detectors ----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_detectors() -> dict[str, object]:
    detectors = build_detectors(make_settings())
    if "face" not in detectors:
        if os.environ.get("OCR_REQUIRE_MODELS") == "1":
            pytest.fail("YuNet model missing (OCR_REQUIRE_MODELS=1); run scripts/fetch_models.sh")
        pytest.skip("YuNet model not installed; set OCR_FACE_MODEL_PATH")
    return detectors  # type: ignore[return-value]


@pytest.fixture
def real_vclient(real_detectors: dict[str, object], real_engines: dict[str, object]) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(), real_engines, real_detectors)) as test_client:  # type: ignore[arg-type]
        yield test_client


def timed(client: TestClient, image: Image.Image, detectors: str) -> tuple[dict, float]:
    data = png(image)
    started = time.perf_counter()
    response = visual(client, data, detectors=detectors)
    assert response.status_code == 200, response.text
    return response.json(), (time.perf_counter() - started) * 1000


def test_face_found_on_public_domain_portrait(real_vclient: TestClient) -> None:
    body, ms = timed(real_vclient, mona(), "face")
    (face,) = body["boxes"]
    assert face["type"] == "FACE" and face["score"] >= 0.8 and not face["needs_review"]
    assert contains(face["bbox"], (125, 85, 190, 170)), face  # eyes to chin of the painting
    print(f"\nPERF face 330x492: {ms:.0f} ms")


def test_small_face_in_large_image_is_found_and_reviewed(real_vclient: TestClient) -> None:
    scene = Image.new("RGB", (3000, 2000), (235, 235, 230))
    scene.paste(mona().resize((110, 164)), (2100, 1300))  # face ~25 px wide
    body, ms = timed(real_vclient, scene, "face")
    faces = [b for b in body["boxes"] if b["type"] == "FACE"]
    assert len(faces) == 1 and faces[0]["needs_review"], body
    assert contains(faces[0]["bbox"], (2142, 1330, 2163, 1355))
    print(f"\nPERF face 3000x2000 (tiled): {ms:.0f} ms")


def test_no_face_on_text_page(real_vclient: TestClient) -> None:
    page = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(page)
    for n in range(60):
        draw.text((150, 150 + n * 52), f"Mario Rossi, via Roma {n}, 00100 Roma - tel. 333 123 45{n:02d} (o0O8@)",
                  fill="black", font=font(34))
    body, ms = timed(real_vclient, page, "face,code")
    assert body["boxes"] == []
    print(f"\nPERF face+code A4@300dpi text page: {ms:.0f} ms")


def test_qr_and_barcode_always_reported(real_vclient: TestClient) -> None:
    scene = Image.new("RGB", (1600, 1000), "white")
    qr, bar = qr_image(), barcode_image()
    scene.paste(qr, (120, 140))
    scene.paste(bar, (800, 600))
    body, ms = timed(real_vclient, scene, "code")
    by_type = {b["type"]: b for b in body["boxes"]}
    assert set(by_type) == {"QR_CODE", "BARCODE"}, body
    assert contains(by_type["QR_CODE"]["bbox"], (120, 140, 120 + qr.width, 140 + qr.height))
    bx = by_type["BARCODE"]["bbox"]
    assert bx[0] <= 820 and bx[2] >= 800 + bar.width - 20  # bars covered end to end
    assert "ABC123" not in str(body) and "PSEUDORA" not in str(body)  # content never returned
    print(f"\nPERF code 1600x1000: {ms:.0f} ms")


def test_rotated_qr_is_found(real_vclient: TestClient) -> None:
    scene = Image.new("RGB", (1000, 1000), "white")
    scene.paste(qr_image().rotate(30, expand=True, fillcolor="white"), (200, 200))
    body, _ = timed(real_vclient, scene, "code")
    assert [b["type"] for b in body["boxes"]] == ["QR_CODE"]


def test_plate_text_is_boxed(real_vclient: TestClient) -> None:
    image, _ = plate_image()
    body, ms = timed(real_vclient, image, "plate")
    (hit,) = body["boxes"]
    assert hit["type"] == "LICENSE_PLATE"
    assert covers_plate_text(hit), hit
    print(f"\nPERF plate 1200x800: {ms:.0f} ms")


def covers_plate_text(hit: dict) -> bool:
    """The box must contain the rendered glyphs of "AB 123 CD" (measured with the same font)."""
    ink = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((450, 530), "AB 123 CD", font=font(64))
    return contains(hit["bbox"], ink)  # type: ignore[arg-type]


def test_all_detectors_together_one_request(real_vclient: TestClient) -> None:
    scene, _ = plate_image()
    scene.paste(mona().resize((220, 328)), (40, 40))
    scene.paste(qr_image(scale=4, border=4), (900, 60))  # real codes keep a quiet zone
    body, ms = timed(real_vclient, scene, "face,code,plate")
    assert sorted(b["type"] for b in body["boxes"]) == ["FACE", "LICENSE_PLATE", "QR_CODE"], body
    print(f"\nPERF face+code+plate 1200x800: {ms:.0f} ms")


# --- /v1/ocr with ``detectors``: one upload, OCR and face/code in parallel, plates from the OCR words ----

def test_ocr_with_detectors_returns_visual_on_the_page(vclient: TestClient) -> None:
    response = post(vclient, png(Image.new("RGB", (400, 300), "white")), detectors="face,code")
    assert response.status_code == 200, response.text
    (page,) = response.json()["pages"]
    assert [b["type"] for b in page["visual"]] == ["FACE", "QR_CODE"]
    assert page["words"]  # the OCR result is unchanged


def test_ocr_without_detectors_keeps_the_old_shape(vclient: TestClient) -> None:
    (page,) = post(vclient, png(Image.new("RGB", (400, 300), "white"))).json()["pages"]
    assert page["visual"] is None


def test_ocr_detectors_fail_closed(vclient: TestClient) -> None:
    data = png(Image.new("RGB", (64, 64), "white"))
    assert post(vclient, data, detectors="eyes").json()["error"] == "INVALID_PARAMETER"
    two = pdf(Image.new("RGB", (200, 200), "white"), Image.new("RGB", (200, 200), "white"), resolution=100)
    assert post(vclient, two, detectors="face").json()["error"] == "INVALID_PARAMETER"  # one page only


def test_ocr_detector_crash_fails_the_request() -> None:
    class Broken(FakeDetector):
        def detect(self, image: Image.Image) -> list[Hit]:
            raise RuntimeError("face model crashed")

    app = create_app(make_settings(), {"tesseract": FakeEngine()}, {"face": Broken([]), "code": FakeDetector([])})
    with TestClient(app, raise_server_exceptions=False) as client:
        response = post(client, png(Image.new("RGB", (64, 64), "white")), detectors="face")
    assert response.status_code == 500 and "visual" not in response.text


def test_plates_from_the_ocr_words_match_the_visual_endpoint(real_vclient: TestClient) -> None:
    image, _ = plate_image()
    data = png(image)
    response = post(real_vclient, data, detectors="plate", engine="rapidocr")
    assert response.status_code == 200, response.text
    (hit,) = response.json()["pages"][0]["visual"]
    assert hit["type"] == "LICENSE_PLATE" and covers_plate_text(hit), hit


def test_all_detectors_in_the_ocr_call(real_vclient: TestClient) -> None:
    scene, _ = plate_image()
    scene.paste(mona().resize((220, 328)), (40, 40))
    scene.paste(qr_image(scale=4, border=4), (900, 60))
    started = time.perf_counter()
    response = post(real_vclient, png(scene), detectors="face,code,plate", engine="rapidocr", marks="signature,stamp")
    assert response.status_code == 200, response.text
    page = response.json()["pages"][0]
    assert sorted(b["type"] for b in page["visual"]) == ["FACE", "LICENSE_PLATE", "QR_CODE"], page["visual"]
    print(f"\nPERF ocr+face+code+plate 1200x800: {(time.perf_counter() - started) * 1000:.0f} ms")
