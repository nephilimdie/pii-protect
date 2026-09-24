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


settings = Settings()
os.environ.setdefault("HF_HOME", settings.model_cache_dir)
os.environ.setdefault("TRANSFORMERS_CACHE", settings.model_cache_dir)
