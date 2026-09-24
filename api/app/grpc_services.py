"""gRPC service registration for the generated protobuf messages."""
from __future__ import annotations

import grpc

from app.grpc_generated import pii_protect_pb2 as pb


class AnonymizationServicer:
    async def Anonymize(self, request, context):
        raise NotImplementedError

    async def AnonymizeBatch(self, request, context):
        raise NotImplementedError

    async def Detect(self, request, context):
        raise NotImplementedError

    async def Ping(self, request, context):
        raise NotImplementedError


def add_AnonymizationServicer_to_server(servicer, server) -> None:
    handlers = {
        "Anonymize": _handler(servicer.Anonymize, pb.AnonymizeRequest, pb.AnonymizeResponse),
        "AnonymizeBatch": _handler(servicer.AnonymizeBatch, pb.AnonymizeBatchRequest, pb.AnonymizeBatchResponse),
        "Detect": _handler(servicer.Detect, pb.DetectRequest, pb.DetectResponse),
        "Ping": _handler(servicer.Ping, pb.PingRequest, pb.PingResponse),
    }
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "pii_protect.v1.Anonymization", handlers,
    ),))


class AdminConfigServicer:
    async def ListConfig(self, request, context):
        raise NotImplementedError

    async def GetConfig(self, request, context):
        raise NotImplementedError

    async def SetConfig(self, request, context):
        raise NotImplementedError

    async def DeleteConfig(self, request, context):
        raise NotImplementedError


def add_AdminConfigServicer_to_server(servicer, server) -> None:
    handlers = {
        "ListConfig": _handler(servicer.ListConfig, pb.ListConfigRequest, pb.ListConfigResponse),
        "GetConfig": _handler(servicer.GetConfig, pb.GetConfigRequest, pb.ConfigItem),
        "SetConfig": _handler(servicer.SetConfig, pb.SetConfigRequest, pb.ConfigItem),
        "DeleteConfig": _handler(servicer.DeleteConfig, pb.DeleteConfigRequest, pb.DeleteConfigResponse),
    }
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "pii_protect.v1.AdminConfig", handlers,
    ),))


class StatsServicer:
    async def GetStats(self, request, context):
        raise NotImplementedError


def add_StatsServicer_to_server(servicer, server) -> None:
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "pii_protect.v1.Stats",
        {"GetStats": _handler(servicer.GetStats, pb.StatsRequest, pb.StatsResponse)},
    ),))


def _handler(method, request_type, response_type):
    return grpc.unary_unary_rpc_method_handler(
        method,
        request_deserializer=request_type.FromString,
        response_serializer=response_type.SerializeToString,
    )
