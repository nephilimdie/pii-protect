from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentAnonymizationResult:
    """Redacted document and non-sensitive page region metadata."""

    document: bytes
    content_type: str
    pages: int
    regions: list[dict[str, object]]
