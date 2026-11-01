"""FastAPI app: ``POST /v1/ocr``, ``/health``, ``/readiness``. Contract: ocr-service/openapi.yaml."""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.config import Settings
from app.engines import Engine
from app.errors import ErrorCode, OcrError
from app.inputs import open_document
from app.pipeline import ENGINES, Pipeline

logger = logging.getLogger("ocr.api")
_LANG_RE = re.compile(r"^[a-z_]{3,8}(\+[a-z_]{3,8}){0,3}$")
_KEY_HEADER = "x-internal-key"
_FORM_OVERHEAD = 64 * 1024  # multipart boundaries + small fields


def build_engines(settings: Settings) -> dict[str, Engine]:
    """Why: concrete engines are created once per process (ONNX sessions are expensive).
    What: Tesseract always; RapidOCR when its models are present (readiness reports absence).
    Test: with a missing model dir the mapping only contains "tesseract".
    """
    from app.engines.tesseract import Tesseract

    engines: dict[str, Engine] = {"tesseract": Tesseract(settings.tesseract_cmd, settings.tessdata_dir)}
    if (settings.rapidocr_model_dir / "det.onnx").is_file():
        from app.engines.rapid import RapidOcr

        engines["rapidocr"] = RapidOcr(settings.rapidocr_model_dir, settings.rapidocr_max_side)
    return engines


def _error(status: int, code: str, message: str, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Why: one flat error shape for every failure. What: ``{"error", "message"}``. Test: body keys."""
    return JSONResponse({"error": code, "message": message}, status_code=status, headers=dict(headers or {}))


async def _read_capped(request: Request, limit: int) -> bytes:
    """Why: the body must never exceed the budget in RAM, even without Content-Length (chunked).
    What: streams the body, failing with 413 as soon as ``limit`` is crossed.
    Test: a 2 MB body with limit 1 MB raises FILE_TOO_LARGE.
    """
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise OcrError(413, ErrorCode.FILE_TOO_LARGE, "The upload exceeds the maximum file size.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _parse_form(request: Request, settings: Settings) -> tuple[bytes, dict[str, str]]:
    """Why: Starlette spools uploads >1 MB to a temp file on disk; documents may hold PII, so
    the body is capped first and the spool limit raised above the cap (RAM-only, guaranteed).
    What: returns (file bytes, text fields). Test: a 5 MB upload performs no file-system writes.
    """
    if "multipart/form-data" not in request.headers.get("content-type", ""):
        raise OcrError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Send multipart/form-data with a 'file' part.")
    limit = settings.max_file_bytes + _FORM_OVERHEAD
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise OcrError(413, ErrorCode.FILE_TOO_LARGE, "The upload exceeds the maximum file size.")
    body = await _read_capped(request, limit)

    async def stream() -> AsyncIterator[bytes]:
        yield body
        yield b""

    parser = MultiPartParser(request.headers, stream(), max_files=1, max_fields=8, max_part_size=4096)
    parser.spool_max_size = limit + 1
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, "Malformed multipart body.") from exc
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, "The 'file' part is required.")
    data = await upload.read()
    await upload.close()
    if len(data) > settings.max_file_bytes:
        raise OcrError(413, ErrorCode.FILE_TOO_LARGE, "The upload exceeds the maximum file size.")
    fields = {k: v for k, v in form.multi_items() if isinstance(v, str)}
    return data, fields


def _options(fields: Mapping[str, str], settings: Settings, languages: frozenset[str]) -> tuple[int, str, str, str | None]:
    """Why: all parameters are untrusted. What: validated (dpi, lang, engine, pages).
    Test: dpi=50 -> INVALID_PARAMETER; lang="ita+xxx" -> INVALID_PARAMETER; engine="foo" -> same.
    """
    dpi_raw = fields.get("dpi", str(settings.default_dpi))
    if not dpi_raw.isdigit() or not settings.min_dpi <= int(dpi_raw) <= settings.max_dpi:
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"dpi must be an integer {settings.min_dpi}-{settings.max_dpi}.")
    lang = fields.get("lang", "ita+eng")
    if not _LANG_RE.match(lang) or not set(lang.split("+")) <= languages:
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"lang must combine installed languages: {sorted(languages)}.")
    engine = fields.get("engine", "auto")
    if engine not in ENGINES:
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"engine must be one of {list(ENGINES)}.")
    return int(dpi_raw), lang, engine, fields.get("pages")


def create_app(settings: Settings | None = None, engines: Mapping[str, Engine] | None = None) -> FastAPI:
    """Why: app factory = dependency injection point (tests pass fake engines and settings).
    What: wires auth, concurrency gate, headers, error handlers and routes.
    Test: ``TestClient(create_app(Settings(internal_api_key="k"), fakes)).get("/health")`` -> 200.
    """
    settings = settings or Settings()
    state: dict[str, Mapping[str, Engine]] = {}
    gate = asyncio.Semaphore(settings.workers)
    limiter = anyio.CapacityLimiter(settings.workers)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state["engines"] = engines if engines is not None else build_engines(settings)
        yield

    app = FastAPI(title="Pseudora OCR service", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Why: OCR output is PII; nothing may be cached. What: no-store + nosniff on all responses."""
        try:
            response = await call_next(request)
        except OcrError as exc:  # raised before routing (never in practice) -> still flat
            response = _error(exc.status, exc.code, exc.message, exc.headers)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(OcrError)
    async def ocr_error(_: Request, exc: OcrError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(404)
    async def not_found(_: Request, __: Exception) -> JSONResponse:
        return _error(404, ErrorCode.NOT_FOUND, "Not found.")

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unexpected failure: %s", type(exc).__name__)  # type only: messages may echo content
        response = _error(500, ErrorCode.OCR_FAILED, "OCR failed.")
        response.headers["Cache-Control"] = "no-store"  # runs outside the header middleware
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readiness")
    async def readiness() -> JSONResponse:
        current = state.get("engines", {})
        checks = {name: await anyio.to_thread.run_sync(engine.ready) for name, engine in current.items()}
        ok = bool(settings.internal_api_key) and {"tesseract", "rapidocr"} <= set(checks) and all(c.get("ok") for c in checks.values())
        body = {"status": "ready" if ok else "not_ready", "engines": checks,
                "auth_configured": bool(settings.internal_api_key), "workers": settings.workers}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.post("/v1/ocr")
    async def ocr(request: Request) -> Response:
        if not settings.internal_api_key:
            raise OcrError(503, ErrorCode.NOT_READY, "The service has no internal API key configured.")
        if not hmac.compare_digest(request.headers.get(_KEY_HEADER, "").encode(), settings.internal_api_key.encode()):
            raise OcrError(401, ErrorCode.UNAUTHORIZED, "Missing or invalid X-Internal-Key.")
        try:
            await asyncio.wait_for(gate.acquire(), timeout=settings.busy_timeout_seconds)
        except TimeoutError as exc:
            raise OcrError(503, ErrorCode.BUSY, "All OCR workers are busy; retry later.",
                           {"Retry-After": str(settings.retry_after_seconds)}) from exc
        try:
            started = time.monotonic()
            deadline = started + settings.timeout_seconds
            data, fields = await _parse_form(request, settings)
            engines_now = state["engines"]
            languages_of = getattr(engines_now.get("tesseract"), "languages", None)
            languages = languages_of() if callable(languages_of) else frozenset({"ita", "eng"})
            dpi, lang, engine, pages = _options(fields, settings, languages)
            pipeline = Pipeline(settings, engines_now)

            def work() -> bytes:
                document = open_document(data, settings, dpi, pages)
                return pipeline.run(document, engine, lang, deadline).model_dump_json().encode()

            payload = await anyio.to_thread.run_sync(work, limiter=limiter)
            logger.info("ocr ok engine=%s ms=%d", engine, (time.monotonic() - started) * 1000)
            return Response(payload, media_type="application/json")
        finally:
            gate.release()

    return app


def app_factory() -> FastAPI:
    """Why: uvicorn ``--factory`` entry point so import never reads env or loads models.
    What: ``create_app()`` with env settings. Test: ``uvicorn app.main:app_factory --factory`` boots.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
