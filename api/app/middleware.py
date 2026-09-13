from __future__ import annotations

import json
import logging
import os
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)
_MAX_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(6 * 1024 * 1024)))


class JsonFormatter(logging.Formatter):
    _EXTRA_FIELDS = ("request_id", "tenant_id", "status")

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": "request_body_too_large", "max_bytes": _MAX_BODY_BYTES},
                status_code=413,
            )
        return await call_next(request)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        response.headers["X-Request-Id"] = request_id
        tenant_id = request.headers.get("x-pii-tenant-id") or getattr(
            request.state, "tenant_id", None
        )
        logger.info(
            "%s %s %s %.1fms",
            request.method, request.url.path, response.status_code, duration_ms,
            extra={"request_id": request_id, "tenant_id": tenant_id, "status": response.status_code},
        )
        return response
