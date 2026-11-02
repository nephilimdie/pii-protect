"""Runtime settings for the OCR service (env prefix ``OCR_``)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Why: every limit that bounds memory/CPU must be tunable per deployment without a rebuild.
    What: typed, range-checked env configuration; defaults fit a 4-CPU / 4 GiB container.
    Test: ``Settings(internal_api_key="k", workers=0)`` raises a ValidationError.
    """

    model_config = SettingsConfigDict(env_prefix="OCR_", extra="ignore")

    internal_api_key: str = Field(default="", min_length=0)
    workers: int = Field(default=4, ge=1, le=64)
    busy_timeout_seconds: float = Field(default=1.0, ge=0, le=60)
    retry_after_seconds: int = Field(default=5, ge=1, le=600)
    timeout_seconds: float = Field(default=120.0, gt=0, le=3600)

    max_file_bytes: int = Field(default=20_000_000, ge=1_000, le=500_000_000)
    max_pages: int = Field(default=20, ge=1, le=1000)
    max_page_pixels: int = Field(default=20_000_000, ge=100_000, le=200_000_000)
    max_input_pixels: int = Field(default=100_000_000, ge=1_000_000, le=1_000_000_000)
    default_dpi: int = Field(default=300, ge=72, le=600)
    min_dpi: int = Field(default=100, ge=20, le=600)
    max_dpi: int = Field(default=600, ge=72, le=1200)

    tesseract_cmd: str = "tesseract"
    tessdata_root: Path = Path("/opt/ocr-models/tessdata")
    tessdata_variant: str = Field(default="fast", pattern=r"^(fast|best)$")
    rapidocr_model_dir: Path = Path("/opt/ocr-models/rapidocr")
    rapidocr_max_side: int = Field(default=2000, ge=320, le=8000)

    low_conf_threshold: float = Field(default=60.0, ge=0, le=100)
    adaptive_conf_threshold: float = Field(default=80.0, ge=0, le=100)
    max_passes: int = Field(default=3, ge=1, le=5)
    auto_fallback_conf: float = Field(default=70.0, ge=0, le=100)
    max_skew_degrees: float = Field(default=10.0, ge=0, le=45)
    osd_min_confidence: float = Field(default=2.0, ge=0, le=100)

    face_model_path: Path = Path("/opt/ocr-models/yunet/face_detection_yunet_2023mar.onnx")
    face_threshold: float = Field(default=0.6, ge=0.05, le=1)  # 0.5 added FPs on paintings, no recall; < face_review_score is reviewed
    face_review_score: float = Field(default=0.8, ge=0, le=1)
    face_review_side: int = Field(default=32, ge=0, le=1000)  # faces smaller than this (px) are reviewed
    plate_review_conf: float = Field(default=80.0, ge=0, le=100)
    visual_max_side: int = Field(default=4000, ge=640, le=10000)  # visual detection runs on <= this copy

    @property
    def tessdata_dir(self) -> Path:
        """Why: one image ships both fast and best models; the variant picks the directory.
        What: ``tessdata_root / tessdata_variant``.
        Test: variant "best" with root /x yields /x/best.
        """
        return self.tessdata_root / self.tessdata_variant
