from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import anonymize as module
from app.routers._anonymize_models import BatchAnonymizeRequest


@pytest.mark.asyncio
async def test_batch_does_not_expose_fail_open_original_text(monkeypatch):
    monkeypatch.setattr(module, "_process_anonymization", AsyncMock(side_effect=[
        SimpleNamespace(safe=False, anonymized_text="private-value", warnings=[]),
        SimpleNamespace(safe=True, anonymized_text="[PERSON_1]", warnings=[]),
    ]))
    body = BatchAnonymizeRequest(items=[
        {"id": "a", "text": "private-value"}, {"id": "b", "text": "Alice"},
    ])
    result = await module.anonymize_batch(
        body, request=None, api_key=None, db=None, anonymizer=None,
        tenant_id="tenant-a", key_provider=None,
    )
    assert result.items[0].status == "failed"
    assert result.items[0].output is None
    assert result.items[0].error_code == "PII_PROCESSING_FAILED"
    assert result.items[1].output == "[PERSON_1]"
    assert "private-value" not in result.model_dump_json()
