import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(**overrides):
    values = {
        "database_url": "postgresql+asyncpg://pii:pii@localhost/pii",
        "encryption_key": "test-encryption-key",
        "admin_initial_key": "test-admin-key",
    }
    values.update(overrides)
    return Settings(**values)


def test_residency_defaults_to_explicitly_unspecified():
    settings = _settings()

    assert settings.data_residency_region == "unspecified"
    assert settings.require_data_residency is False
    assert settings.model_cache_dir == "/root/.cache/huggingface"


def test_residency_enforcement_requires_a_region():
    with pytest.raises(ValidationError, match="PII_DATA_RESIDENCY_REGION"):
        _settings(require_data_residency=True)


def test_residency_region_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        _settings(data_residency_region="eu central")
