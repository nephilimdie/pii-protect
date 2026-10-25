from __future__ import annotations

import os
from typing import Any
from pydantic import AliasChoices, BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_settings() -> "Settings":
    return settings


class LayerConfig(BaseModel):
    enabled: bool = True
    priority: int = 10


class Settings(BaseSettings):
    database_url: str
    encryption_key: str
    admin_initial_key: str
    failure_mode: str = Field(default="closed", validation_alias=AliasChoices("FAILURE_MODE", "PII_FAILURE_MODE"))
    batch_max_items: int = Field(default=50, validation_alias=AliasChoices("BATCH_MAX_ITEMS", "PII_BATCH_MAX_ITEMS"))
    multitenancy_enabled: bool = Field(default=False, validation_alias=AliasChoices("MULTITENANCY_ENABLED", "PII_MULTITENANCY_ENABLED"))
    engine_exposure: str = Field(default="self_hosted", validation_alias=AliasChoices("PII_ENGINE_EXPOSURE"))
    accept_tenant_header: bool = Field(default=False, validation_alias=AliasChoices("PII_ACCEPT_TENANT_HEADER"))
    spacy_model: str = "it_core_news_lg"
    privacy_filter_model: str = "openai/privacy-filter"
    privacy_filter_revision: str = "7ffa9a043d54d1be65afb281eddf0ffbe629385b"
    ai4privacy_model: str = "Isotonic/distilbert_finetuned_ai4privacy_v2"
    ai4privacy_revision: str = "11795a7549030bb5a21832b09e712b19d39045a7"
    model_cache_dir: str = Field(
        default="/root/.cache/huggingface",
        min_length=1,
        validation_alias=AliasChoices("MODEL_CACHE_DIR", "PII_MODEL_CACHE_DIR"),
    )
    data_residency_region: str = Field(
        default="unspecified",
        pattern=r"^(?:unspecified|[a-z0-9][a-z0-9-]{1,31})$",
        validation_alias=AliasChoices("DATA_RESIDENCY_REGION", "PII_DATA_RESIDENCY_REGION"),
    )
    require_data_residency: bool = Field(
        default=False,
        validation_alias=AliasChoices("REQUIRE_DATA_RESIDENCY", "PII_REQUIRE_DATA_RESIDENCY"),
    )
    mapping_ttl_days: int = 30
    mapping_ttl_hours: int = Field(
        default=1,
        ge=1,
        le=24 * 365,
        validation_alias=AliasChoices("MAPPING_TTL_HOURS", "PII_MAPPING_TTL_HOURS"),
    )
    cors_allowed_origins: str = Field(default="", validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "PII_CORS_ALLOWED_ORIGINS"))
    internal_api_key: str = Field(default="", validation_alias=AliasChoices("PII_INTERNAL_API_KEY"))
    default_tenant_id: str | None = Field(default=None, validation_alias=AliasChoices("PII_DEFAULT_TENANT_ID"))
    async_job_worker_api_url: str = Field(default="http://127.0.0.1:8000", validation_alias=AliasChoices("ASYNC_JOB_WORKER_API_URL"))
    async_job_poll_seconds: float = Field(default=1.0, ge=0.1, le=60, validation_alias=AliasChoices("ASYNC_JOB_POLL_SECONDS"))
    async_job_max_attempts: int = Field(default=3, ge=1, le=10, validation_alias=AliasChoices("ASYNC_JOB_MAX_ATTEMPTS"))
    async_job_webhook_hosts: str = Field(default="", validation_alias=AliasChoices("ASYNC_JOB_WEBHOOK_HOSTS"))
    plugin_dir: str = Field(default="./plugins", validation_alias=AliasChoices("PLUGIN_DIR"))
    marketplace_url: str = Field(default="", validation_alias=AliasChoices("MARKETPLACE_URL"))
    marketplace_token: str = Field(default="", validation_alias=AliasChoices("MARKETPLACE_TOKEN"))
    marketplace_public_key: str = Field(default="", validation_alias=AliasChoices("MARKETPLACE_PUBLIC_KEY"))
    marketplace_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, validation_alias=AliasChoices("MARKETPLACE_TIMEOUT_SECONDS"))
    marketplace_max_package_bytes: int = Field(default=50_000_000, ge=1_000_000, le=500_000_000, validation_alias=AliasChoices("MARKETPLACE_MAX_PACKAGE_BYTES"))
    image_max_bytes: int = Field(default=4_000_000, ge=1_024, le=100_000_000, validation_alias=AliasChoices("IMAGE_MAX_BYTES", "PII_IMAGE_MAX_BYTES"))
    image_max_pixels: int = Field(default=25_000_000, ge=1_000_000, le=200_000_000, validation_alias=AliasChoices("IMAGE_MAX_PIXELS", "PII_IMAGE_MAX_PIXELS"))
    document_max_bytes: int = Field(default=4_000_000, ge=1_024, le=100_000_000, validation_alias=AliasChoices("DOCUMENT_MAX_BYTES", "PII_DOCUMENT_MAX_BYTES"))
    document_max_pages: int = Field(default=10, ge=1, le=100, validation_alias=AliasChoices("DOCUMENT_MAX_PAGES", "PII_DOCUMENT_MAX_PAGES"))
    # Zero-retention document service (/v1/documents/*).
    document_upload_max_bytes: int = Field(default=20_000_000, ge=1_024, le=200_000_000, validation_alias=AliasChoices("DOCUMENT_UPLOAD_MAX_BYTES", "PII_DOCUMENT_UPLOAD_MAX_BYTES"))
    document_upload_max_pages: int = Field(default=200, ge=1, le=2_000, validation_alias=AliasChoices("DOCUMENT_UPLOAD_MAX_PAGES", "PII_DOCUMENT_UPLOAD_MAX_PAGES"))
    document_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0, validation_alias=AliasChoices("DOCUMENT_TIMEOUT_SECONDS", "PII_DOCUMENT_TIMEOUT_SECONDS"))
    document_pdf_dpi: int = Field(default=200, ge=72, le=400, validation_alias=AliasChoices("DOCUMENT_PDF_DPI", "PII_DOCUMENT_PDF_DPI"))
    document_pdf_max_page_pixels: int = Field(default=16_000_000, ge=1_000_000, le=100_000_000, validation_alias=AliasChoices("DOCUMENT_PDF_MAX_PAGE_PIXELS", "PII_DOCUMENT_PDF_MAX_PAGE_PIXELS"))
    document_pdf_min_dpi: int = Field(default=50, ge=20, le=300, validation_alias=AliasChoices("DOCUMENT_PDF_MIN_DPI", "PII_DOCUMENT_PDF_MIN_DPI"))
    document_max_text_chars: int = Field(default=500_000, ge=1_000, le=5_000_000, validation_alias=AliasChoices("DOCUMENT_MAX_TEXT_CHARS", "PII_DOCUMENT_MAX_TEXT_CHARS"))
    document_detection_window_chars: int = Field(default=6_000, ge=500, le=100_000, validation_alias=AliasChoices("DOCUMENT_DETECTION_WINDOW_CHARS", "PII_DOCUMENT_DETECTION_WINDOW_CHARS"))
    document_detection_window_overlap: int = Field(default=300, ge=50, le=5_000, validation_alias=AliasChoices("DOCUMENT_DETECTION_WINDOW_OVERLAP", "PII_DOCUMENT_DETECTION_WINDOW_OVERLAP"))
    document_max_concurrent_jobs: int = Field(default=2, ge=1, le=64, validation_alias=AliasChoices("DOCUMENT_MAX_CONCURRENT_JOBS", "PII_DOCUMENT_MAX_CONCURRENT_JOBS"))
    document_busy_timeout_seconds: float = Field(default=2.0, ge=0.0, le=60.0, validation_alias=AliasChoices("DOCUMENT_BUSY_TIMEOUT_SECONDS", "PII_DOCUMENT_BUSY_TIMEOUT_SECONDS"))
    document_max_rss_mb: int = Field(default=0, ge=0, le=1_000_000, validation_alias=AliasChoices("DOCUMENT_MAX_RSS_MB", "PII_DOCUMENT_MAX_RSS_MB"))
    document_docx_max_uncompressed_bytes: int = Field(default=100_000_000, ge=1_000_000, le=1_000_000_000, validation_alias=AliasChoices("DOCUMENT_DOCX_MAX_UNCOMPRESSED_BYTES", "PII_DOCUMENT_DOCX_MAX_UNCOMPRESSED_BYTES"))
    document_docx_max_ratio: int = Field(default=100, ge=10, le=10_000, validation_alias=AliasChoices("DOCUMENT_DOCX_MAX_RATIO", "PII_DOCUMENT_DOCX_MAX_RATIO"))
    document_docx_max_entries: int = Field(default=1_000, ge=10, le=100_000, validation_alias=AliasChoices("DOCUMENT_DOCX_MAX_ENTRIES", "PII_DOCUMENT_DOCX_MAX_ENTRIES"))
    # Window detection runs in one shared pool; inference_threads=0 sizes torch/ONNX intra-op threads to fit it.
    document_detection_workers: int = Field(default=min(4, os.cpu_count() or 1), ge=1, le=64, validation_alias=AliasChoices("DOCUMENT_DETECTION_WORKERS", "PII_DOCUMENT_DETECTION_WORKERS"))
    inference_threads: int = Field(default=0, ge=0, le=256, validation_alias=AliasChoices("INFERENCE_THREADS", "PII_INFERENCE_THREADS"))
    # In-memory document jobs (/v1/documents/jobs): RAM only, deleted on delivery, failure, cancel or idle TTL.
    document_job_ttl_seconds: int = Field(default=900, ge=10, le=86_400, validation_alias=AliasChoices("DOCUMENT_JOB_TTL_SECONDS", "PII_DOCUMENT_JOB_TTL_SECONDS"))
    document_job_max_text_chars: int = Field(default=500_000, ge=1_000, le=5_000_000, validation_alias=AliasChoices("DOCUMENT_JOB_MAX_TEXT_CHARS", "PII_DOCUMENT_JOB_MAX_TEXT_CHARS"))
    document_max_jobs: int = Field(default=20, ge=1, le=1_000, validation_alias=AliasChoices("DOCUMENT_MAX_JOBS", "PII_DOCUMENT_MAX_JOBS"))
    document_max_job_bytes_total: int = Field(default=1_000_000_000, ge=1_000_000, le=64_000_000_000, validation_alias=AliasChoices("DOCUMENT_MAX_JOB_BYTES_TOTAL", "PII_DOCUMENT_MAX_JOB_BYTES_TOTAL"))
    grpc_enabled: bool = Field(default=False, validation_alias=AliasChoices("GRPC_ENABLED", "PII_GRPC_ENABLED"))
    grpc_host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("GRPC_HOST", "PII_GRPC_HOST"))
    grpc_port: int = Field(default=50051, ge=1, le=65535, validation_alias=AliasChoices("GRPC_PORT", "PII_GRPC_PORT"))

    # Each key matches a layer_name. To disable a layer: set enabled=false in env.
    detection_layers: dict[str, dict[str, Any]] = {
        "presidio":       {"enabled": True},
        "privacy_filter": {"enabled": True},
        "ai4privacy":     {"enabled": True},
        "regex":          {"enabled": True},
    }

    def inference_thread_count(self) -> int:
        """Intra-op threads per model call: explicit setting, else CPUs / window workers rounded up
        (measured: rounding down to 1 thread costs single-window latency ~1.6x for ~6% more parallel throughput)."""
        return self.inference_threads or max(1, -(-(os.cpu_count() or 1) // self.document_detection_workers))

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
        populate_by_name=True,
        protected_namespaces=(),
    )

    @model_validator(mode="after")
    def validate_residency(self) -> "Settings":
        if self.require_data_residency and self.data_residency_region == "unspecified":
            raise ValueError("PII_DATA_RESIDENCY_REGION is required when residency enforcement is enabled")
        return self

    def layer_enabled(self, name: str) -> bool:
        """Why: one source of truth for which detector layers startup loads and readiness requires.
        What: True unless detection_layers[name].enabled is explicitly false (unknown layers default on).
        Test: Settings(detection_layers={"presidio": {"enabled": False}}).layer_enabled("presidio") is False.
        """
        return bool(self.detection_layers.get(name, {}).get("enabled", True))


settings = Settings()
os.environ.setdefault("HF_HOME", settings.model_cache_dir)
os.environ.setdefault("TRANSFORMERS_CACHE", settings.model_cache_dir)
