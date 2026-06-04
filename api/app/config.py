from typing import Any
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class LayerConfig(BaseModel):
    enabled: bool = True
    priority: int = 10


class Settings(BaseSettings):
    database_url: str
    encryption_key: str
    admin_initial_key: str
    spacy_model: str = "it_core_news_lg"
    privacy_filter_model: str = "openai/privacy-filter"
    ai4privacy_model: str = "Isotonic/distilbert_finetuned_ai4privacy_v2"
    mapping_ttl_days: int = 30

    # Each key matches a layer_name. To disable a layer: set enabled=false in env.
    detection_layers: dict[str, dict[str, Any]] = {
        "presidio":       {"enabled": True},
        "privacy_filter": {"enabled": True},
        "ai4privacy":     {"enabled": True},
        "regex":          {"enabled": True},
    }

    class Config:
        env_file = ".env"


settings = Settings()
