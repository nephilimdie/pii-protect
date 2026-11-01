"""Flat error contract: every failure is ``{"error": CODE, "message": text}``."""
from __future__ import annotations


class ErrorCode:
    """Why: error codes are part of the API contract (the engine maps them to its own codes).
    What: the closed set of ``error`` values the service returns.
    Test: grep openapi.yaml; every constant here appears in the ErrorCode enum there.
    """

    UNAUTHORIZED = "UNAUTHORIZED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_DOCUMENT = "INVALID_DOCUMENT"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    PAGE_TOO_LARGE = "PAGE_TOO_LARGE"
    BUSY = "BUSY"
    NOT_READY = "NOT_READY"
    TIMEOUT = "OCR_TIMEOUT"
    OCR_FAILED = "OCR_FAILED"
    NOT_FOUND = "NOT_FOUND"


class OcrError(Exception):
    """Why: one exception type carries status + code so handlers render a single flat shape.
    What: raised anywhere in the request path; the app turns it into a JSON error response.
    Test: ``OcrError(413, ErrorCode.FILE_TOO_LARGE, "x").status == 413``.
    """

    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
