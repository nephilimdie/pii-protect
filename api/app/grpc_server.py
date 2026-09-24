"""Optional gRPC facade over the authenticated FastAPI API."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import grpc
import httpx

from app.config import settings
from app.grpc_generated import pii_protect_pb2 as pb
from app import grpc_services as rpc
from app.identity.api_key_service import ApiKeyService

Json = dict[str, Any]


def _json(value: str | bytes) -> Any:
    if not value:
        return None
    return json.loads(value)


def _metadata(context: grpc.aio.ServicerContext) -> dict[str, str]:
    return {key.lower(): value for key, value in context.invocation_metadata()}


def _headers(metadata: dict[str, str]) -> dict[str, str]:
    headers = {"x-api-key": metadata.get("x-api-key", "")}
    for key in ("x-pii-tenant-id", "x-router-auth"):
        if metadata.get(key):
            headers[key] = metadata[key]
    return headers


class GrpcBridge:
    """Common authenticated ASGI bridge used by all gRPC services."""

    def __init__(self, app: Any):
        self._app = app

    async def authorize(
        self,
        context: grpc.aio.ServicerContext,
        roles: tuple[str, ...],
    ) -> dict[str, str]:
        metadata = _metadata(context)
        plain_key = metadata.get("x-api-key", "")
        if not plain_key:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing_api_key")

        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            api_key = await ApiKeyService(db).verify(plain_key)
        if api_key is None:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid_api_key")
        if api_key.role not in roles:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "insufficient_role")
        return metadata

    async def request(
        self,
        context: grpc.aio.ServicerContext,
        method: str,
        path: str,
        body: Json | None = None,
        query: dict[str, str] | None = None,
    ) -> Json:
        metadata = _metadata(context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url="http://grpc.local",
        ) as client:
            response = await client.request(
                method,
                path,
                json=body,
                params=query,
                headers=_headers(metadata),
            )
        if response.is_error:
            detail = response.json() if response.content else response.reason_phrase
            await context.abort(grpc.StatusCode.UNKNOWN, json.dumps(detail, default=str))
        value = response.json()
        return value if isinstance(value, dict) else {}


def _entity(value: Json) -> pb.PiiEntity:
    return pb.PiiEntity(
        entity_type=str(value.get("type", value.get("entity_type", ""))),
        start=int(value.get("start", 0)),
        end=int(value.get("end", 0)),
        score=float(value.get("confidence", value.get("score", 0.0))),
        original=str(value.get("value", value.get("original", ""))),
        replacement=str(value.get("replacement", "")),
    )


def _policy(value: Json | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


class AnonymizationService(rpc.AnonymizationServicer):
    def __init__(self, bridge: GrpcBridge):
        self._bridge = bridge

    async def Anonymize(self, request: pb.AnonymizeRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("service", "admin"))
        body: Json = {
            "text": request.text,
            "context_id": request.context_id,
            "context_type": request.context_type or None,
            "domain": request.domain or None,
            "language": request.language or None,
            "mode": request.mode or None,
            "dry_run": request.dry_run,
            "project_id": request.project_id or "default",
            "policy": _json(request.policy_json),
        }
        result = await self._bridge.request(context, "POST", "/v1/anonymize", body)
        return pb.AnonymizeResponse(
            text=str(result.get("anonymized_text", "")),
            anonymized_text=str(result.get("anonymized_text", "")),
            entity_count=int(result.get("entity_count", 0)),
            pii_types_found=result.get("pii_types_found", []),
            entities=[_entity(item) for item in result.get("entities", [])],
            mode=str(result.get("mode", "")),
            safe=bool(result.get("safe", False)),
            dry_run=bool(result.get("dry_run", False)),
            warnings=result.get("warnings") or [],
            policy_json=_policy(result.get("policy")),
        )

    async def AnonymizeBatch(self, request: pb.AnonymizeBatchRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("service", "admin"))
        body = {
            "context_type": request.context_type or "default",
            "language": request.language or None,
            "mode": request.mode or None,
            "policy": _json(request.policy_json),
            "dry_run": request.dry_run,
            "items": [
                {
                    "id": item.id,
                    "text": item.text,
                    "context_type": item.context_type or None,
                    "language": item.language or None,
                    "mode": item.mode or None,
                    "policy": _json(item.policy_json),
                    "dry_run": item.dry_run,
                }
                for item in request.items
            ],
        }
        result = await self._bridge.request(context, "POST", "/v1/anonymize/batch", body)
        return pb.AnonymizeBatchResponse(
            items=[
                pb.BatchResult(
                    id=str(item.get("id", "")),
                    status=str(item.get("status", "")),
                    output=str(item.get("output") or ""),
                    error_code=str(item.get("error_code") or ""),
                    warnings=item.get("warnings") or [],
                )
                for item in result.get("items", [])
            ]
        )

    async def Detect(self, request: pb.DetectRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("service", "admin"))
        result = await self._bridge.request(
            context,
            "POST",
            "/v1/detect",
            {
                "text": request.text,
                "context_type": request.context_type or "default",
                "language": request.language or None,
                "policy": _json(request.policy_json),
            },
        )
        return pb.DetectResponse(
            entities=[_entity(item) for item in result.get("entities", [])],
            entity_count=int(result.get("entity_count", 0)),
            pii_types_found=result.get("pii_types_found", []),
        )

    async def Ping(self, request: pb.PingRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("service", "admin"))
        return pb.PingResponse(ok=True, version="1.0.0")


class AdminConfigService(rpc.AdminConfigServicer):
    def __init__(self, bridge: GrpcBridge):
        self._bridge = bridge

    async def ListConfig(self, request: pb.ListConfigRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("admin",))
        result = await self._bridge.request(
            context,
            "GET",
            f"/v1/admin/scoped-config/{quote(request.collection, safe='-_.')}" ,
            query={
                "scope_type": request.scope_type or "tenant",
                "scope_key": request.scope_key,
                "q": request.q,
            },
        )
        return pb.ListConfigResponse(items=[_config_item(item) for item in result.get("items", [])])

    async def GetConfig(self, request: pb.GetConfigRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("admin",))
        result = await self._bridge.request(
            context,
            "GET",
            f"/v1/admin/scoped-config/{quote(request.collection, safe='-_.')}",
            query={
                "scope_type": request.scope_type or "tenant",
                "scope_key": request.scope_key,
                "q": request.key,
            },
        )
        for item in result.get("items", []):
            if item.get("key") == request.key:
                return _config_item(item)
        await context.abort(grpc.StatusCode.NOT_FOUND, "config_not_found")

    async def SetConfig(self, request: pb.SetConfigRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("admin",))
        path = f"/v1/admin/scoped-config/{quote(request.collection, safe='-_.')}/{quote(request.key, safe='-_.') }"
        result = await self._bridge.request(
            context,
            "PUT",
            path,
            {
                "scope_type": request.scope_type,
                "scope_key": request.scope_key,
                "action": request.action,
                "data": _json(request.data_json.decode()),
                "item_key": request.key,
            },
        )
        return _config_item(result)

    async def DeleteConfig(self, request: pb.DeleteConfigRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("admin",))
        path = f"/v1/admin/scoped-config/{quote(request.collection, safe='-_.')}/{quote(request.key, safe='-_.') }"
        await self._bridge.request(
            context,
            "DELETE",
            path,
            query={"scope_type": request.scope_type or "tenant", "scope_key": request.scope_key},
        )
        return pb.DeleteConfigResponse(success=True)


def _config_item(value: Json) -> pb.ConfigItem:
    data = value.get("data", value)
    return pb.ConfigItem(
        key=str(value.get("key", value.get("item_key", ""))),
        data_json=json.dumps(data, ensure_ascii=False).encode(),
    )


class StatsService(rpc.StatsServicer):
    def __init__(self, bridge: GrpcBridge):
        self._bridge = bridge

    async def GetStats(self, request: pb.StatsRequest, context: grpc.aio.ServicerContext):
        await self._bridge.authorize(context, ("auditor", "admin"))
        result = await self._bridge.request(context, "GET", "/v1/admin/stats")
        return pb.StatsResponse(
            total_anonymizations=int(result.get("total_anonymizations", 0)),
            total_tokens_created=int(result.get("total_tokens_created", 0)),
            requests_last_24h=int(result.get("requests_last_24h", 0)),
            usage_events_total=int(result.get("usage_events_total", 0)),
            usage_chars_in_total=int(result.get("usage_chars_in_total", 0)),
            pii_types_breakdown={k: int(v) for k, v in result.get("pii_types_breakdown", {}).items()},
        )


async def start_grpc_server(app: Any, host: str, port: int) -> grpc.aio.Server:
    server = grpc.aio.server()
    bridge = GrpcBridge(app)
    rpc.add_AnonymizationServicer_to_server(AnonymizationService(bridge), server)
    rpc.add_AdminConfigServicer_to_server(AdminConfigService(bridge), server)
    rpc.add_StatsServicer_to_server(StatsService(bridge), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    return server
