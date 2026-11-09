"""Photos and screenshots (JPEG/PNG/WebP) through the OCR service: sync endpoints and jobs.

Two synthetic inputs with known word boxes: a chat/e-mail screenshot (PNG) and a "photo"
(JPEG: noisy paper, stored sideways with EXIF orientation 6, GPS + camera EXIF). A fake OCR
service answers with those boxes scaled to the image it receives, plus one low-confidence and
one unrecognized-ink region. Pixel sampling on the output proves what was blacked out; PIL and
the raw bytes prove no metadata survived. `test_real_ocr_*` need PII_OCR_TEST_URL (CI).
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont, ImageStat

from app.config import settings
from app.documents.image_handler import sniff_image
from app.documents.models import DocumentError
from app.documents.ocr_client import OcrClient
from app.routers import documents as documents_module
from tests.unit import test_documents as base
from tests.unit.test_document_jobs import _create, _get, _render, _wait, jobs  # noqa: F401  (fixture reuse)
from tests.unit.test_documents import EMAIL, PERSON, _post, env  # noqa: F401  (fixture reuse)

IBAN = "IT60X0542811101000000123456"
PHONE = "+39 347 123 4567"
KEY = "test-internal-key"
SECRETS = ("Mario", "Rossi", f"<{EMAIL}>", "+39", "347", "123", "4567", IBAN)
KEPT = ("Da:", "Tel:", "IBAN:", "Ciao", "bonifico.")
GPS_LAT = (45.0, 26.0, 13.37)


class Layout:
    """An upright image with known word boxes (text, box, line) and two review regions."""

    def __init__(self, size, lines, font_size, background, low, ink, noise=False, angle=0.0) -> None:
        self.size, self.low, self.ink = size, low, ink
        font = ImageFont.load_default(size=font_size)
        image = Image.new("RGB", size, background)
        if noise:  # textured "paper" photo: grain everywhere, then the text
            grain = Image.effect_noise(size, 40).convert("RGB")
            image = Image.blend(image, grain, 0.25)
        layer = Image.new("L", size, 0)  # text ink as a mask, so it can be rotated like a tilted photo
        draw = ImageDraw.Draw(layer)
        self.words = []
        for line, text in enumerate(lines):
            x, y = 60, 120 + line * round(font_size * 2.2)
            for token in text.split(" "):
                box = draw.textbbox((x, y), token, font=font)
                draw.text((x, y), token, font=font, fill=255)
                self.words.append((token, self._turn(box, angle), line))
                x = box[2] + draw.textlength(" ", font=font)
        if angle:
            layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(size[0] / 2, size[1] / 2))
        image.paste((20, 20, 30), mask=layer)
        draw = ImageDraw.Draw(image)
        draw.rectangle(low, fill=(150, 150, 150))  # a smudge the OCR could not read confidently
        draw.line((ink[0], ink[3] - 8, ink[2], ink[1] + 8), fill=(0, 0, 0), width=8)  # a signature
        self.image = image

    def _turn(self, box, angle):
        """Axis-aligned envelope of `box` rotated by `angle` degrees (PIL: counter-clockwise) about the centre."""
        if not angle:
            return box
        cx, cy = self.size[0] / 2, self.size[1] / 2
        a = math.radians(angle)
        xs, ys = [], []
        for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
            dx, dy = x - cx, y - cy
            xs.append(cx + dx * math.cos(a) + dy * math.sin(a))
            ys.append(cy - dx * math.sin(a) + dy * math.cos(a))
        return (math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))

    def box(self, token):
        return next(box for text, box, _ in self.words if text == token)


CHAT = ["Da: Mario Rossi <" + EMAIL + ">", f"Tel: {PHONE}", f"IBAN: {IBAN}", "Ciao Giulia, ti mando i dati per il bonifico."]
SCREENSHOT = Layout((1280, 720), CHAT, 22, (245, 246, 250), low=(900, 560, 1100, 600), ink=(100, 600, 500, 680))
PHOTO = Layout((1200, 1600), CHAT, 30, (232, 226, 214), low=(700, 1100, 1000, 1150), ink=(100, 1300, 600, 1400),
               noise=True)


def png(image: Image.Image, **params) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", **params)
    return out.getvalue()


def photo_jpeg(layout: Layout = PHOTO, quality: int = 90) -> bytes:
    """Stored sideways (as a phone held in portrait writes it) with EXIF orientation 6 + GPS + camera."""
    stored = layout.image.transpose(Image.Transpose.ROTATE_90)  # orientation 6 turns it back upright
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F], exif[0x0110] = "PseudoPhone", "Model X Pro"
    gps = exif.get_ifd(0x8825)
    gps.update({1: "N", 2: GPS_LAT, 3: "E", 4: (9.0, 11.0, 2.0)})
    out = io.BytesIO()
    stored.save(out, format="JPEG", quality=quality, exif=exif.tobytes(), comment=b"Mario Rossi's phone")
    return out.getvalue()


class FakeOcr:
    """The OCR service contract, answering with `layout`'s boxes scaled to the received image."""

    def __init__(self, layout: Layout) -> None:
        self.layout, self.calls, self.fail_with, self.sizes, self.engines = layout, 0, None, [], []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        body = request.content
        image = Image.open(io.BytesIO(body[body.index(b"\x89PNG"):]))
        self.sizes.append((image.size, image.mode))
        self.engines.append(re.search(rb'name="engine"\r\n\r\n(\w+)', body).group(1).decode())
        f = image.width / self.layout.size[0]

        def scale(box):
            return [min(max(0, round(v * f)), image.width if i % 2 == 0 else image.height) for i, v in enumerate(box)]

        words = [{"text": t, "conf": 93.0, "bbox": scale(b), "line_id": n, "block_id": 0} for t, b, n in self.layout.words]
        return httpx.Response(200, json={"pages": [{
            "index": 0, "width": image.width, "height": image.height, "dpi": 300, "engine": "tesseract",
            "words": words, "lines": [{"id": n, "bbox": [0, 0, 1, 1], "text": t} for n, t in enumerate(CHAT)],
            "low_conf_regions": [scale(self.layout.low)], "ink_without_text_regions": [scale(self.layout.ink)]}]})


@pytest.fixture
def img(env, monkeypatch):  # noqa: F811
    env.fake = FakeOcr(SCREENSHOT)
    client = OcrClient("http://ocr:8090", KEY, 30, 1, 10, transport=httpx.MockTransport(lambda r: env.fake(r)),
                       sleep=lambda _: None)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    monkeypatch.setitem(base._PATTERNS, IBAN, "IBAN")
    monkeypatch.setitem(base._PATTERNS, PHONE, "PHONE")
    return env


def _mean(image: Image.Image, box) -> float:
    return ImageStat.Stat(image.convert("L").crop(box)).mean[0]


def _assert_redacted(image: Image.Image, layout: Layout, kept_review=(), dark: float = 20) -> None:
    assert image.size == layout.size and image.mode == "RGB"
    for token in SECRETS:
        assert _mean(image, layout.box(token)) < dark, token  # opaque box over every PII word
    for token in KEPT:
        assert _mean(image, layout.box(token)) > 120, token  # the rest stays readable
    for n, region in enumerate((layout.low, layout.ink)):
        assert (_mean(image, region) > 120) if n in kept_review else (_mean(image, region) < dark), n


def _assert_no_metadata(payload: bytes) -> None:
    out = Image.open(io.BytesIO(payload))
    assert not out.getexif() and not out.getexif().get_ifd(0x8825)
    assert not {"exif", "icc_profile", "xmp", "XML:com.adobe.xmp", "comment", "photoshop"} & set(out.info)
    assert not getattr(out, "text", {})
    for marker in (b"Exif\x00\x00", b"PseudoPhone", b"Model X Pro", b"Mario", b"ICC_PROFILE", b"<x:xmpmeta"):
        assert marker not in payload, marker


# ── format sniffing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("head, expected", [
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "png"), (b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpeg"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"), (b"BMW e Audi: listino prezzi 2026", None), (b"Mario Rossi", None),
])
def test_sniff_image(head, expected):
    assert sniff_image(head) == expected


@pytest.mark.parametrize("head", [
    b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00",
    b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00", b"GIF89a\x01\x00", b"II*\x00\x08\x00", b"MM\x00*\x00\x00",
    b"BM" + b"\x00" * 12 + (40).to_bytes(4, "little"), b"\x00\x00\x00\x0cjP  \r\n\x87\n",
])
def test_unsupported_image_formats_get_415(env, head):  # noqa: F811
    with pytest.raises(DocumentError) as caught:
        sniff_image(head)
    assert caught.value.status == 415 and caught.value.code == "IMAGE_FORMAT_UNSUPPORTED"
    r = _post(env, "redact", head + b"\x00" * 64)
    assert r.status_code == 415 and r.json()["error"] == "IMAGE_FORMAT_UNSUPPORTED"


def test_ocr_disabled_rejects_images(env):  # noqa: F811
    r = _post(env, "redact", png(SCREENSHOT.image))
    assert r.status_code == 422 and r.json()["error"] == "IMAGE_OCR_NOT_ENABLED"


# ── sync endpoints ───────────────────────────────────────────────────────────

def test_screenshot_png_redact_end_to_end(img):
    r = _post(img, "redact", png(SCREENSHOT.image), domain="hr_payroll")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png" and r.headers["x-pii-document-format"] == "png"
    assert 'filename="redacted.png"' in r.headers["content-disposition"]
    assert "image_ocr_applied" in r.headers["x-pii-warnings"] and r.headers["x-pseudora-pages"] == "1"
    assert "exif_gps" in r.headers["x-pii-sanitized"] and r.headers["x-pii-entity-count"] == "4"
    out = Image.open(io.BytesIO(r.content))
    assert out.format == "PNG"
    _assert_redacted(out, SCREENSHOT)
    _assert_no_metadata(r.content)
    assert img.fake.sizes == [((1280, 720), "RGB")]  # native resolution, colour (stamp hues)
    assert img.fake.engines == ["rapidocr"]  # PII_OCR_IMAGE_ENGINE default (scanned PDFs keep `auto`)


def test_photo_jpeg_exif_orientation_and_gps_removed(img):
    img.fake.layout = PHOTO
    source = photo_jpeg()
    assert Image.open(io.BytesIO(source)).getexif().get_ifd(0x8825)  # the input really carries GPS
    r = _post(img, "redact", source)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/jpeg" and "image_metadata_removed" in r.headers["x-pii-warnings"]
    out = Image.open(io.BytesIO(r.content))
    assert out.format == "JPEG" and out.size == PHOTO.size  # displayed upright: stored size was swapped
    _assert_redacted(out, PHOTO, dark=30)
    _assert_no_metadata(r.content)
    assert img.fake.sizes == [(PHOTO.size, "RGB")]  # OCR saw the upright frame (colour)


def test_sync_redact_review_keep_leaves_only_kept_regions_visible(img):
    source = png(SCREENSHOT.image)
    kept = _post(img, "redact", source, review_keep="[1]")  # the user checked the signature
    assert kept.status_code == 200, kept.text
    _assert_redacted(Image.open(io.BytesIO(kept.content)), SCREENSHOT, kept_review=(1,))
    both = _post(img, "redact", source, review_keep="[0, 1]")
    _assert_redacted(Image.open(io.BytesIO(both.content)), SCREENSHOT, kept_review=(0, 1))  # text PII still black
    _assert_redacted(Image.open(io.BytesIO(_post(img, "redact", source, review_keep="[]").content)), SCREENSHOT)
    calls = img.fake.calls
    for bad in ("[-1]", "[true]", "[1.0]", '{"0": 1}', "1", "x"):
        r = _post(img, "redact", source, review_keep=bad)
        assert r.status_code == 422 and r.json()["error"] == "INVALID_REVIEW_KEEP", bad
    assert img.fake.calls == calls  # a malformed field is refused before any OCR
    unknown = _post(img, "redact", source, review_keep="[2]")
    assert unknown.status_code == 422 and unknown.json()["error"] == "INVALID_REVIEW_KEEP"
    assert unknown.headers["content-type"].startswith("application/json")  # never an image
    assert _post(img, "preview", source, review_keep="x").status_code == 200  # ignored outside redact


def _frac(layout: Layout, box) -> list[float]:
    w, h = layout.size
    return [box[0] / w, box[1] / h, box[2] / w, box[3] / h]


def test_sync_redact_review_default_visible_review_cover_and_user_areas(img):
    source = png(SCREENSHOT.image)
    shown = _post(img, "redact", source, review_default="visible")
    assert shown.status_code == 200, shown.text
    _assert_redacted(Image.open(io.BytesIO(shown.content)), SCREENSHOT, kept_review=(0, 1))  # text PII still black
    one = _post(img, "redact", source, review_default="visible", review_cover="[1]")
    _assert_redacted(Image.open(io.BytesIO(one.content)), SCREENSHOT, kept_review=(0,))
    area = SCREENSHOT.box("Ciao")
    drawn = _post(img, "redact", source, review_default="visible",
                  cover_boxes=json.dumps([{"page": 1, "bbox": _frac(SCREENSHOT, area)}]))
    out = Image.open(io.BytesIO(drawn.content))
    assert _mean(out, area) < 20 and _mean(out, SCREENSHOT.box("bonifico.")) > 120  # only the user's area
    calls = img.fake.calls
    for field, value, code in (("review_default", "sometimes", "INVALID_REVIEW_DEFAULT"),
                               ("review_cover", "[-1]", "INVALID_REVIEW_COVER"), ("review_cover", "x", "INVALID_REVIEW_COVER"),
                               ("cover_boxes", '[{"page": 1, "bbox": [0.5, 0.1, 0.4, 0.2]}]', "INVALID_COVER_BOXES"),
                               ("cover_boxes", '[{"page": 0, "bbox": [0.1, 0.1, 0.4, 0.2]}]', "INVALID_COVER_BOXES"),
                               ("cover_boxes", '{"page": 1}', "INVALID_COVER_BOXES")):
        r = _post(img, "redact", source, **{field: value})
        assert r.status_code == 422 and r.json()["error"] == code, (field, value, r.text)
    assert img.fake.calls == calls  # malformed fields are refused before any OCR
    for fields, code in (({"review_default": "visible", "review_keep": "[0]"}, "INVALID_REVIEW_KEEP"),
                         ({"review_default": "visible", "review_cover": "[2]"}, "INVALID_REVIEW_COVER"),
                         ({"cover_boxes": '[{"page": 2, "bbox": [0.1, 0.1, 0.4, 0.2]}]'}, "INVALID_COVER_BOXES"),
                         ({"cover_boxes": json.dumps([{"page": 1, "bbox": [0, 0, 0.1, 0.1]}] * 201)}, "INVALID_COVER_BOXES")):
        r = _post(img, "redact", source, **fields)
        assert r.status_code == 422 and r.json()["error"] == code, (fields, r.text)
        assert r.headers["content-type"].startswith("application/json")  # never an image


def test_image_job_render_review_default_visible_with_user_area(img_jobs):
    job_id = _create(img_jobs, png(SCREENSHOT.image)).json()["job_id"]
    assert _wait(img_jobs, job_id)["status"] == "ready"
    bad = _render(img_jobs, job_id, review_default="visible", review_keep=[0])
    assert bad.status_code == 422 and bad.json()["error"] == "INVALID_RENDER_REQUEST"
    assert _render(img_jobs, job_id, cover_boxes=[{"page": 1, "bbox": [0.5, 0.5, 0.4, 0.6]}]).status_code == 422
    area = SCREENSHOT.box("Ciao")
    rendered = _render(img_jobs, job_id, review_default="visible", review_cover=[0],
                       cover_boxes=[{"page": 1, "bbox": _frac(SCREENSHOT, area)}])
    assert rendered.status_code == 200, rendered.text
    out = Image.open(io.BytesIO(rendered.content))
    assert _mean(out, SCREENSHOT.low) < 20 and _mean(out, SCREENSHOT.ink) > 120 and _mean(out, area) < 20


def test_preview_payload_has_scanned_pdf_shape(img):
    r = _post(img, "preview", png(SCREENSHOT.image))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "png" and body["pages"] == 1 and body["ocr_pages"] == [1]
    found = {e["text"]: e for e in body["entities"]}
    assert set(found) == {PERSON, EMAIL, PHONE, IBAN}
    w, h = SCREENSHOT.size
    left, top = SCREENSHOT.box("Mario")[:2]
    right, bottom = SCREENSHOT.box("Rossi")[2:]
    [box] = found[PERSON]["boxes"]
    assert box["page"] == 1 and found[PERSON]["page"] == 1
    assert box["bbox"] == pytest.approx([left / w, top / h, right / w, bottom / h], abs=0.002)
    assert [(b["id"], b["page"], b["reason"]) for b in body["needs_review"]] == [
        (0, 1, "low_confidence"), (1, 1, "unrecognized_ink")]
    assert body["needs_review"][1]["bbox"] == pytest.approx(
        [SCREENSHOT.ink[0] / w, SCREENSHOT.ink[1] / h, SCREENSHOT.ink[2] / w, SCREENSHOT.ink[3] / h], abs=0.002)


def test_webp_round_trip_and_alpha_flattened(img):
    rgba = SCREENSHOT.image.convert("RGBA")
    rgba.putalpha(255)
    hidden = Image.new("RGBA", (120, 40), (0, 0, 0, 0))  # fully transparent pixels hiding black "ink"
    rgba.paste(hidden, (1150, 20, 1270, 60))
    out = io.BytesIO()
    rgba.save(out, format="WEBP", lossless=True)
    r = _post(img, "redact", out.getvalue())
    assert r.status_code == 200, r.text
    result = Image.open(io.BytesIO(r.content))
    assert r.headers["content-type"] == "image/webp" and result.format == "WEBP" and result.mode == "RGB"
    _assert_redacted(result.convert("RGB"), SCREENSHOT, dark=30)
    assert _mean(result, (1150, 20, 1270, 60)) > 240  # what was transparent is white, not the hidden pixels


def test_large_image_is_downscaled_for_ocr_and_boxes_map_back(img, monkeypatch):
    monkeypatch.setattr(settings, "document_pdf_max_page_pixels", 230_400)  # 640 x 360 budget
    r = _post(img, "redact", png(SCREENSHOT.image))
    assert r.status_code == 200, r.text
    [((width, height), _)] = img.fake.sizes
    assert width * height <= 230_400 and width < 1280
    _assert_redacted(Image.open(io.BytesIO(r.content)).convert("RGB"), SCREENSHOT)  # output keeps full size


def test_pixel_limit_animation_and_corruption(img, monkeypatch):
    monkeypatch.setattr(settings, "document_image_max_pixels", 1_000_000)
    r = _post(img, "redact", png(Image.new("RGB", (1001, 1000), "white")))
    assert r.status_code == 413 and r.json().items() >= {
        "error": "IMAGE_PIXEL_LIMIT_EXCEEDED", "max_pixels": 1_000_000, "pixels": 1_001_000}.items()
    frames = [Image.new("RGB", (64, 64), c) for c in ("white", "black")]
    out = io.BytesIO()
    frames[0].save(out, format="PNG", save_all=True, append_images=frames[1:])  # APNG
    r = _post(img, "redact", out.getvalue())
    assert r.status_code == 422 and r.json()["error"] == "IMAGE_ANIMATED_UNSUPPORTED"
    r = _post(img, "redact", png(SCREENSHOT.image)[:3000])  # truncated
    assert r.status_code == 422 and r.json()["error"] == "INVALID_DOCUMENT"
    assert img.fake.calls == 0  # every refusal happens before OCR


def test_file_size_limit(img, monkeypatch):
    monkeypatch.setattr(settings, "document_upload_max_bytes", 50_000)
    r = _post(img, "redact", photo_jpeg(quality=95))
    assert r.status_code == 413 and r.json()["error"] == "DOCUMENT_TOO_LARGE" and img.fake.calls == 0


def test_pseudonymize_not_supported_for_images(img):
    r = _post(img, "pseudonymize", png(SCREENSHOT.image))
    assert r.status_code == 422 and r.json()["error"] == "PSEUDONYMIZE_NOT_SUPPORTED_FOR_IMAGE"
    assert img.fake.calls == 0


@pytest.mark.parametrize("error, status, code", [
    (httpx.ConnectError("refused"), 503, "OCR_UNAVAILABLE"),
    (httpx.ReadTimeout("slow"), 504, "OCR_TIMEOUT"),
])
def test_ocr_down_fails_closed_without_returning_the_image(img, error, status, code):
    img.fake.fail_with = error
    for op in ("redact", "preview"):
        r = _post(img, op, png(SCREENSHOT.image))
        assert r.status_code == status and r.json()["error"] == code, r.text
        assert r.headers["content-type"].startswith("application/json") and b"PNG" not in r.content


def test_no_text_found(img):
    img.fake.layout = Layout((300, 200), [], 20, "white", low=(0, 0, 0, 0), ink=(0, 0, 0, 0))
    img.fake.layout.words = []
    r = _post(img, "redact", png(Image.new("RGB", (300, 200), "white")))
    assert r.status_code == 422 and r.json()["error"] == "OCR_NO_TEXT_FOUND"


def test_logs_never_contain_ocr_text_gps_or_key(img, caplog):
    source = photo_jpeg()  # built before capturing: only the engine's own logs are inspected
    caplog.set_level(logging.DEBUG)
    img.fake.layout = PHOTO
    _post(img, "redact", source)
    img.fake.fail_with = httpx.ConnectError(f"refused {PERSON}")
    _post(img, "redact", source)
    for secret in (PERSON, EMAIL, IBAN, PHONE, KEY, "PseudoPhone", "13.37"):
        assert secret not in caplog.text


# ── jobs ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def img_jobs(img, jobs):  # noqa: F811
    return jobs


def test_image_job_lifecycle_with_review_keep(img_jobs):
    img_jobs.fake.layout = PHOTO
    created = _create(img_jobs, photo_jpeg())
    assert created.status_code == 202, created.text
    assert created.json()["format"] == "jpeg" and created.json()["pages_total"] == 1
    job_id = created.json()["job_id"]
    status = _wait(img_jobs, job_id)
    assert status["status"] == "ready", status
    assert status["ocr_pages_total"] == status["ocr_pages_done"] == 1 and status["pages_done"] == 1
    preview = _get(img_jobs, f"{job_id}/entities").json()
    assert preview["ocr_pages"] == [1] and len(preview["needs_review"]) == 2
    assert _render(img_jobs, job_id, review_keep=[2]).status_code == 422
    bad = _render(img_jobs, job_id, mode="pseudonymize")
    assert bad.status_code == 422 and bad.json()["error"] == "PSEUDONYMIZE_NOT_SUPPORTED_FOR_IMAGE"
    rendered = _render(img_jobs, job_id, review_keep=[1])  # the user checked the signature
    assert rendered.status_code == 200, rendered.text
    assert rendered.headers["content-type"] == "image/jpeg"
    _assert_redacted(Image.open(io.BytesIO(rendered.content)), PHOTO, kept_review=(1,), dark=30)
    _assert_no_metadata(rendered.content)
    assert _get(img_jobs, job_id).status_code == 404 and len(img_jobs.store) == 0


def test_image_job_ocr_failure_leaves_failed_tombstone(img_jobs):
    img_jobs.fake.fail_with = httpx.ConnectError("refused")
    job_id = _create(img_jobs, png(SCREENSHOT.image)).json()["job_id"]
    status = _wait(img_jobs, job_id)
    assert status["status"] == "failed" and status["error"]["error"] == "OCR_UNAVAILABLE"
    assert _get(img_jobs, f"{job_id}/entities").status_code == 409


# ── real OCR container (CI: ci-engine.yml starts ocr-service and sets PII_OCR_TEST_URL) ──

REAL_URL = os.environ.get("PII_OCR_TEST_URL")


@pytest.fixture
def real(env, monkeypatch):  # noqa: F811
    client = OcrClient(REAL_URL, os.environ.get("PII_OCR_TEST_KEY", "ci-key"), 120, 3, 10)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    monkeypatch.setitem(base._PATTERNS, IBAN, "IBAN")
    monkeypatch.setitem(base._PATTERNS, PHONE, "PHONE")
    return env


TILTED = Layout((1200, 1600), CHAT, 30, (232, 226, 214), low=(0, 0, 0, 0), ink=(0, 0, 0, 0), noise=True, angle=3.0)


@pytest.mark.skipif(not REAL_URL, reason="PII_OCR_TEST_URL not set (no OCR container)")
@pytest.mark.parametrize("name, payload, layout", [
    ("screenshot", lambda: png(SCREENSHOT.image), SCREENSHOT),
    ("tilted_photo", lambda: photo_jpeg(TILTED), TILTED),
])
def test_real_ocr_redacts_screenshot_and_photo(real, name, payload, layout):
    text = _post(real, "preview", payload()).json()["text"]
    entities = []  # detector-independent: the OCR must read each secret (spacing aside), then boxes must cover it
    for secret, pii_type in ((PERSON, "PERSON"), (EMAIL, "EMAIL"), (PHONE, "PHONE"), (IBAN, "IBAN")):
        match = re.search(r"\s*".join(map(re.escape, secret.replace(" ", ""))), text)
        assert match, (name, secret, text)
        entities.append({"start": match.start(), "end": match.end(), "type": pii_type})
    r = _post(real, "redact", payload(), entities=json.dumps(entities))
    assert r.status_code == 200, r.text
    out = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert out.size == layout.size
    for token in SECRETS:
        assert _mean(out, layout.box(token)) < 40, (name, token)
    _assert_no_metadata(r.content)
