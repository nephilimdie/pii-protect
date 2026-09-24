from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, AliasChoices
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
    ai4privacy_model: str = "Isotonic/distilbert_finetuned_ai4privacy_v2"
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

    # Each key matches a layer_name. To disable a layer: set enabled=false in env.
    detection_layers: dict[str, dict[str, Any]] = {
        "presidio":       {"enabled": True},
        "privacy_filter": {"enabled": True},
        "ai4privacy":     {"enabled": True},
        "regex":          {"enabled": True},
    }

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_nested_delimiter="__")


settings = Settings()
