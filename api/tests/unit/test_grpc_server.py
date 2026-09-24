from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.grpc_generated import pii_protect_pb2 as pb
from app.grpc_server import GrpcBridge, AnonymizationService, _headers


class _Context:
    def __init__(self, metadata: tuple[tuple[str, str], ...] = ()):
        self._metadata = metadata

    def invocation_metadata(self):
        return self._metadata

    async def abort(self, _code, detail):
        raise ValueError(detail)


@pytest.mark.asyncio
async def test_grpc_anonymize_reuses_authenticated_http_contract():
    app = FastAPI()

    @app.post("/v1/anonymize")
    async def anonymize(body: dict):
        assert body["context_type"] == "support_ticket"
        return {
            "anonymized_text": "Hello [EMAIL_1]",
            "entity_count": 1,
            "pii_types_found": ["EMAIL"],
            "entities": [{
                "type": "EMAIL", "start": 6, "end": 16,
                "confidence": 1.0, "value": "a@example.com",
                "replacement": "[EMAIL_1]",
            }],
            "mode": "tag",
            "safe": True,
            "dry_run": False,
            "policy": {"id": "support_ticket"},
        }

    bridge = GrpcBridge(app)

    async def allow(_context, _roles):
        return {"x-api-key": "test-key"}

    bridge.authorize = allow
    service = AnonymizationService(bridge)
    response = await service.Anonymize(
        pb.AnonymizeRequest(
            text="Hello a@example.com",
            context_id="case-1",
            context_type="support_ticket",
            language="en",
            mode="tag",
        ),
        _Context((("x-api-key", "test-key"),)),
    )

    assert response.anonymized_text == "Hello [EMAIL_1]"
    assert response.entity_count == 1
    assert response.entities[0].entity_type == "EMAIL"
    assert response.entities[0].original == "a@example.com"


@pytest.mark.asyncio
async def test_grpc_ping_requires_authentication_metadata():
    bridge = GrpcBridge(FastAPI())
    service = AnonymizationService(bridge)

    with pytest.raises(ValueError, match="missing_api_key"):
        await service.Ping(pb.PingRequest(), _Context())


def test_grpc_metadata_is_translated_to_http_headers():
    assert _headers({
        "x-api-key": "key",
        "x-pii-tenant-id": "tenant-a",
        "x-router-auth": "router-secret",
    }) == {
        "x-api-key": "key",
        "x-pii-tenant-id": "tenant-a",
        "x-router-auth": "router-secret",
    }
