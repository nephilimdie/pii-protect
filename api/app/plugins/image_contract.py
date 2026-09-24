from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageAnonymizationResult:
    """Redacted image and non-sensitive region metadata returned by a plugin."""

    image: bytes
    content_type: str
    regions: list[dict[str, object]]
