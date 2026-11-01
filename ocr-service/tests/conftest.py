"""Shared fixtures: settings, fake engine, real engines (models via OCR_TESSDATA_ROOT etc.)."""
from __future__ import annotations

import io
import os
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from app.config import Settings  # noqa: E402
from app.engines import RawWord, remaining  # noqa: E402
from app.main import build_engines, create_app  # noqa: E402

KEY = "test-internal-key"
AUTH = {"X-Internal-Key": KEY}


class FakeEngine:
    """Why: API/limit/fail-closed tests must not depend on OCR models or timing.
    What: returns one confident word per call; can block on an event, sleep, or raise on the
    Nth call. Test: ``FakeEngine().recognize(img, "ita", 300, time.monotonic() + 1)`` -> 1 word.
    """

    name = "tesseract"

    def __init__(self, fail_on_call: int | None = None, sleep: float = 0.0, gate: threading.Event | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.sleep = sleep
        self.gate = gate

    def recognize(self, gray: Image.Image, lang: str, dpi: int, deadline: float) -> list[RawWord]:
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(5)
        if self.sleep:
            time.sleep(self.sleep)
            remaining(deadline)
        if self.fail_on_call == self.calls:
            raise RuntimeError("engine crashed on Mario Rossi")
        return [RawWord("Mario", 95.0, (10, 10, 60, 30), 0, 0), RawWord("Rossi", 40.0, (70, 10, 120, 30), 0, 0)]

    def ready(self) -> dict[str, object]:
        return {"ok": True}

    def languages(self) -> frozenset[str]:
        return frozenset({"ita", "eng"})


def make_settings(**overrides: object) -> Settings:
    """Why/What: settings with the test key and small limits overridable per test. Test: key set."""
    values: dict[str, object] = {"internal_api_key": KEY, "busy_timeout_seconds": 0.05}
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def png(image: Image.Image, **params: object) -> bytes:
    """Why/What: encode an image in memory. Test: starts with the PNG magic."""
    buffer = io.BytesIO()
    image.save(buffer, "PNG", **params)
    return buffer.getvalue()


def pdf(*images: Image.Image, resolution: float = 300.0) -> bytes:
    """Why: Pillow writes simple image PDFs (no extra dependency). What: multi-page PDF bytes."""
    buffer = io.BytesIO()
    images[0].save(buffer, "PDF", save_all=True, append_images=list(images[1:]), resolution=resolution)
    return buffer.getvalue()


def post(client: TestClient, data: bytes, filename: str = "doc.png", headers: dict[str, str] | None = None, **fields: str):  # type: ignore[no-untyped-def]
    """Why/What: one multipart OCR call. Test: returns an httpx Response."""
    return client.post("/v1/ocr", headers=AUTH if headers is None else headers,
                       files={"file": (filename, data, "application/octet-stream")}, data=fields)


@pytest.fixture
def fake() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def client(fake: FakeEngine) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(max_skew_degrees=0), {"tesseract": fake})) as test_client:
        yield test_client


def _real_settings(**overrides: object) -> Settings:
    settings = make_settings(**overrides)
    have = (settings.tessdata_dir / "ita.traineddata").is_file() and (settings.rapidocr_model_dir / "rec.onnx").is_file()
    if not have:
        if os.environ.get("OCR_REQUIRE_MODELS") == "1":
            pytest.fail("OCR models missing (OCR_REQUIRE_MODELS=1); run scripts/fetch_models.sh")
        pytest.skip("OCR models not installed; set OCR_TESSDATA_ROOT / OCR_RAPIDOCR_MODEL_DIR")
    return settings


@pytest.fixture(scope="session")
def real_engines() -> dict[str, object]:
    return build_engines(_real_settings())  # type: ignore[return-value]


@pytest.fixture
def real_client(real_engines: dict[str, object]) -> Iterator[TestClient]:
    with TestClient(create_app(_real_settings(), real_engines)) as test_client:  # type: ignore[arg-type]
        yield test_client
