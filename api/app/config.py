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
    cors_allowed_origins: str = Field(default="", validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "PII_CORS_ALLOWED_ORIGINS"))
    internal_api_key: str = Field(default="", validation_alias=AliasChoices("PII_INTERNAL_API_KEY"))
    default_tenant_id: str | None = Field(default=None, validation_alias=AliasChoices("PII_DEFAULT_TENANT_ID"))

    # Each key matches a layer_name. To disable a layer: set enabled=false in env.
    detection_layers: dict[str, dict[str, Any]] = {
        "presidio":       {"enabled": True},
        "privacy_filter": {"enabled": True},
        "ai4privacy":     {"enabled": True},
        "regex":          {"enabled": True},
    }

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_nested_delimiter="__")


settings = Settings()
