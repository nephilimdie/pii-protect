"""HTTP contract, auth, limits, concurrency, fail-closed and privacy guarantees (fake engine)."""
from __future__ import annotations

import asyncio
import builtins
import io
import logging
import os
import socket
import threading

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from conftest import AUTH, FakeEngine, make_settings, pdf, png, post


def page(width: int = 400, height: int = 300) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    image.paste(0, (20, 20, 200, 40))
    return image


def assert_flat(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error", "message"} and body["error"] == code
    assert response.headers["cache-control"] == "no-store"


def test_health_is_public_and_not_cached(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"


def test_readiness_requires_both_engines(client: TestClient) -> None:
    response = client.get("/readiness")
    assert response.status_code == 503 and response.json()["status"] == "not_ready"


def test_ocr_returns_contract_shape(client: TestClient) -> None:
    response = post(client, png(page()))
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    (result,) = response.json()["pages"]
    assert {"index", "width", "height", "dpi", "engine", "words", "lines", "low_conf_regions", "ink_without_text_regions"} <= set(result)
    assert result["words"][0] == {"text": "Mario", "conf": 95.0, "bbox": [10, 10, 60, 30], "line_id": 0, "block_id": 0}
    assert result["lines"] == [{"id": 0, "bbox": [10, 10, 120, 30], "text": "Mario Rossi"}]
    assert result["low_conf_regions"] == [[70, 10, 120, 30]]
    assert result["ink_without_text_regions"]  # the bar extends beyond the fake word boxes


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Key": "wrong"}])
def test_rejects_missing_or_wrong_key(client: TestClient, headers: dict[str, str]) -> None:
    assert_flat(post(client, png(page()), headers=headers), 401, "UNAUTHORIZED")


def test_fails_closed_without_configured_key(fake: FakeEngine) -> None:
    with TestClient(create_app(make_settings(internal_api_key=""), {"tesseract": fake})) as c:
        assert_flat(post(c, png(page())), 503, "NOT_READY")


@pytest.mark.parametrize("fields,code", [
    ({"dpi": "50"}, "INVALID_PARAMETER"), ({"dpi": "abc"}, "INVALID_PARAMETER"),
    ({"lang": "ita+xxx"}, "INVALID_PARAMETER"), ({"lang": "../../etc"}, "INVALID_PARAMETER"),
    ({"engine": "gpt"}, "INVALID_PARAMETER"), ({"pages": "x"}, "INVALID_PARAMETER"), ({"pages": "2"}, "INVALID_PARAMETER"),
])
def test_rejects_invalid_parameters(client: TestClient, fields: dict[str, str], code: str) -> None:
    assert_flat(post(client, png(page()), **fields), 422, code)


def test_rejects_unsupported_content(client: TestClient) -> None:
    assert_flat(post(client, b"\x00\x01garbage" * 10), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert_flat(client.post("/v1/ocr", headers=AUTH, content=b"{}"), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert_flat(post(client, b""), 422, "INVALID_DOCUMENT")
    assert_flat(post(client, b"%PDF-1.7 broken"), 422, "INVALID_DOCUMENT")


def test_rejects_oversized_upload(fake: FakeEngine) -> None:
    with TestClient(create_app(make_settings(max_file_bytes=2000), {"tesseract": fake})) as c:
        noisy = Image.fromarray(np.random.default_rng(0).integers(0, 255, (300, 300), dtype=np.uint8))
        assert_flat(post(c, png(noisy)), 413, "FILE_TOO_LARGE")
    assert fake.calls == 0


def test_page_limits(fake: FakeEngine) -> None:
    with TestClient(create_app(make_settings(max_pages=2, max_input_pixels=1_000_000), {"tesseract": fake})) as c:
        three = pdf(page(), page(), page())
        assert_flat(post(c, three), 422, "TOO_MANY_PAGES")
        response = post(c, three, pages="2-3")
        assert [p["index"] for p in response.json()["pages"]] == [1, 2]
        assert_flat(post(c, png(Image.new("L", (1100, 1000), 255))), 422, "PAGE_TOO_LARGE")


def test_adaptive_dpi_keeps_page_within_pixel_budget(fake: FakeEngine) -> None:
    settings = make_settings(max_page_pixels=500_000, min_dpi=20)
    with TestClient(create_app(settings, {"tesseract": fake})) as c:
        (result,) = post(c, pdf(Image.new("L", (2480, 3508), 255), resolution=300.0)).json()["pages"]
    assert result["width"] * result["height"] <= 500_000 and result["dpi"] < 300


def test_downscaled_image_reports_boxes_in_original_pixels(fake: FakeEngine) -> None:
    with TestClient(create_app(make_settings(max_page_pixels=250_000), {"tesseract": fake})) as c:
        (result,) = post(c, png(Image.new("L", (1000, 1000), 255))).json()["pages"]
    assert (result["width"], result["height"]) == (1000, 1000)
    assert result["words"][0]["bbox"] == [20, 20, 121, 61]  # fake box (10,10,60,30) at scale ~2.01, rounded outward


def test_exif_orientation_is_applied(client: TestClient) -> None:
    image = Image.new("RGB", (400, 200), "white")
    exif = Image.Exif()
    exif[274] = 6  # rotate 90 CW on display
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    (result,) = post(client, buffer.getvalue(), filename="photo.jpg").json()["pages"]
    assert (result["width"], result["height"]) == (200, 400)


def test_any_page_failure_fails_the_whole_request(caplog: pytest.LogCaptureFixture) -> None:
    engine = FakeEngine(fail_on_call=2)
    with caplog.at_level(logging.INFO), TestClient(create_app(make_settings(), {"tesseract": engine}), raise_server_exceptions=False) as c:
        response = post(c, pdf(page(), page(), page()), filename="Mario_Rossi_CF.pdf")
    assert_flat(response, 500, "OCR_FAILED")
    assert "pages" not in response.text
    assert "Mario" not in caplog.text and "Rossi" not in caplog.text


def test_deadline_returns_504(fake: FakeEngine) -> None:
    engine = FakeEngine(sleep=0.3)
    with TestClient(create_app(make_settings(timeout_seconds=0.1), {"tesseract": engine})) as c:
        assert_flat(post(c, png(page())), 504, "OCR_TIMEOUT")


@pytest.mark.anyio
async def test_busy_returns_503_with_retry_after() -> None:
    gate = threading.Event()
    app = create_app(make_settings(workers=1, busy_timeout_seconds=0.05, retry_after_seconds=7), {"tesseract": FakeEngine(gate=gate)})
    files = {"file": ("a.png", png(page()), "image/png")}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://ocr") as c:
            first = asyncio.create_task(c.post("/v1/ocr", headers=AUTH, files=files))
            await asyncio.sleep(0.2)
            second = await c.post("/v1/ocr", headers=AUTH, files=files)
            gate.set()
            assert (await first).status_code == 200
    assert_flat(second, 503, "BUSY")
    assert second.headers["retry-after"] == "7"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_no_filesystem_writes_for_large_upload(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ~3 MB upload (above Starlette's 1 MB spool threshold) must stay in RAM."""
    writes: list[str] = []
    real_open, real_os_open = builtins.open, os.open

    def guarded_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        if any(flag in mode for flag in "wax+"):
            writes.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):  # type: ignore[no-untyped-def]
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            writes.append(str(path))
        return real_os_open(path, flags, *args, **kwargs)

    big = Image.fromarray(np.random.default_rng(1).integers(0, 255, (1800, 1800), dtype=np.uint8))
    data = png(big)
    assert len(data) > 2_000_000
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    response = post(client, data)
    assert response.status_code == 200, response.text
    assert writes == []


def test_unknown_route_is_flat_404(client: TestClient) -> None:
    assert_flat(client.get("/v2/nope"), 404, "NOT_FOUND")


def _deny(*_: object, **__: object) -> None:
    raise AssertionError("outbound network attempted")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, _deny)
    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(socket, "getaddrinfo", _deny)


def test_request_path_opens_no_sockets(no_network: None, client: TestClient) -> None:
    assert post(client, pdf(page(), page())).status_code == 200
