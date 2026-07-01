from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid

logger = logging.getLogger(__name__)

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.tenant import get_tenant_id
from app.identity.models import ApiKey
from app.config import settings
from app.detection.detector_registry import DetectorRegistry
from app.detection.config_resolver import DetectionConfigResolver
from app.anonymization.anonymizer import PiiAnonymizer
from app.mapping.repository import MappingRepository
from app.mapping.key_provider import EnvKekKeyProvider, KeyProvider
from app.audit.audit_service import AuditService
from app.surrogates.policy_service import PolicyService
from app.surrogates.surrogate_service import SurrogateService
from app.surrogates.generators import language_to_locale
from app.detection.entities import MappingEntry
from app.usage.service import UsageService
from app.routers._anonymize_models import (
    AnonymizeRequest,
    AnonymizeResponse,
    EntityDetail,
    PolicyMetadata,
)


def get_registry(request: Request) -> DetectorRegistry:
    return request.app.state.registry


def _document_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def run_detection(
    anonymizer: PiiAnonymizer,
    text: str,
    context_id: str,
    context_type: str,
    language: str,
):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, anonymizer.detect_only, text, context_id, context_type, language
    )
    return result.entities


def filter_detected_entities(
    entities: list,
    keep_types: set[str] | None = None,
    protect_types: set[str] | None = None,
    always_include_types: set[str] | None = None,
    remove_types: set[str] | None = None,
) -> list:
    keep = keep_types or set()
    # remove entities must pass through the filter so they can be erased
    include_always = (always_include_types or set()) | (remove_types or set())
    filtered = []
    for entity in entities:
        if entity.pii_type in keep:
            continue
        if (
            protect_types is not None
            and entity.pii_type not in protect_types
            and entity.pii_type not in include_always
        ):
            continue
        filtered.append(entity)
    return filtered


async def get_anonymizer(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
) -> PiiAnonymizer:
    from app.detection.layer_settings_repository import LayerSettingsRepository
    resolver = DetectionConfigResolver(db, tenant_id)
    cfg = await resolver.resolve(request.app.state)
    layer_repo = LayerSettingsRepository(db)
    layer_configs = await layer_repo.get_effective(tenant_id)
    return PiiAnonymizer(
        request.app.state.registry,
        denylist=cfg.denylist,
        reclassification_rules=cfg.reclassification_rules,
        regex_patterns=cfg.regex_patterns if tenant_id is not None else None,
        presidio_context=cfg.presidio_context if tenant_id is not None else None,
        enabled_layers=cfg.enabled_layers,
        layer_configs=layer_configs,
    )


def _apply_replacements(
    text: str,
    entities: list,
    mode: str,
    replacement_map: dict[str, str] | None,
    remove_types: set[str] | None = None,
) -> tuple[str, list[MappingEntry]]:
    from app.detection.token_generator import TokenGenerator
    generator = TokenGenerator()
    _remove = remove_types or set()
    stable_map: dict[str, str] = {}

    for entity in entities:
        key = entity.text.lower().strip()
        if key in stable_map:
            continue
        if entity.pii_type in _remove:
            stable_map[key] = ""
        elif mode == "surrogate" and replacement_map:
            stable_map[key] = replacement_map.get(key, entity.text)
        else:
            stable_map[key] = generator.next_token(entity.pii_type)

    mappings: list[MappingEntry] = []
    result = text
    for entity in reversed(entities):
        key = entity.text.lower().strip()
        token = stable_map[key]
        result = result[: entity.start] + token + result[entity.end :]
        mappings.append(
            MappingEntry(
                token=token,
                original=entity.text,
                pii_type=entity.pii_type,
                start=entity.start,
                end=entity.end,
                score=entity.score,
            )
        )

    return result, mappings


async def _build_partial_response(
    body: AnonymizeRequest,
    request: Request,
    anonymizer: PiiAnonymizer,
    policy: dict | None,
) -> AnonymizeResponse | None:
    try:
        lang = body.language or getattr(request.app.state, "default_language", "it")
        entities = await run_detection(
            anonymizer=anonymizer,
            text=body.text,
            context_id=body.context_id,
            context_type=body.context_type,
            language=lang,
        )
        final_text, mappings = _apply_replacements(body.text, entities, "tag", None)
        pii_types = list({m.pii_type for m in mappings})
        return AnonymizeResponse(
            anonymized_text=final_text,
            entity_count=len(mappings),
            pii_types_found=pii_types,
            entities=[
                EntityDetail(
                    type=m.pii_type,
                    start=m.start,
                    end=m.end,
                    confidence=round(m.score, 4),
                    replacement=m.token,
                )
                for m in mappings
            ],
            mode="tag",
            policy=PolicyMetadata(
                id=body.context_type,
                version=policy.get("policy_version") if policy else None,
                hash=policy.get("policy_hash") if policy else None,
            ),
            safe=False,
            dry_run=True,
            warnings=["Partial anonymization result returned after a processing failure."],
        )
    except Exception:
        return None


async def _process_anonymization(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey,
    db: AsyncSession,
    anonymizer: PiiAnonymizer,
    tenant_id: str | None = None,
    key_provider: KeyProvider | None = None,
) -> AnonymizeResponse:
    lang = body.language or getattr(request.app.state, "default_language", "it")
    locale = language_to_locale(lang)
    request_id = uuid.uuid4()
    started_at = time.perf_counter()
    usage_service = UsageService(db)

    try:
        await usage_service.ensure_within_limits(api_key, len(body.text))

        policy_svc = PolicyService(db, tenant_id=tenant_id)
        policy = await policy_svc.resolve(
            context_type=body.context_type,
            inline_policy=body.policy,
            inline_mode=body.mode,
        )
        protect_types = policy["protect_types"]
        keep_types = policy["keep_types"]
        surrogate_types = policy["surrogate_types"]
        remove_types = policy["remove_types"]
        block_types = policy["block_types"]
        resolved_mode = policy["mode"]

        if body.include_entity_values and api_key.role != "admin":
            raise HTTPException(status_code=403, detail="insufficient_role")

        entities = await run_detection(
            anonymizer=anonymizer,
            text=body.text,
            context_id=body.context_id,
            context_type=body.context_type,
            language=lang,
        )

        # Block check runs on ALL detected entities (before policy filtering)
        if block_types:
            blocked = [e.pii_type for e in entities if e.pii_type in block_types]
            if blocked:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "PII_BLOCKED",
                        "message": "Request rejected: blocked PII type(s) detected.",
                        "blocked_types": list(set(blocked)),
                    },
                )

        entities_to_protect = filter_detected_entities(
            entities=entities,
            keep_types=keep_types,
            protect_types=protect_types,
            always_include_types=surrogate_types,
            remove_types=remove_types,
        )

        needs_surrogate = resolved_mode == "surrogate" or bool(surrogate_types)
        if needs_surrogate:
            surrogate_svc = SurrogateService(db, locale=locale)
            replacement_map: dict[str, str] = {}
            for entity in entities_to_protect:
                if resolved_mode != "surrogate" and entity.pii_type not in surrogate_types:
                    continue
                if entity.pii_type in remove_types:
                    continue
                key = entity.text.lower().strip()
                if key not in replacement_map:
                    strategy = await policy_svc.get_faker_strategy(entity.pii_type)
                    replacement_map[key] = await surrogate_svc.get_or_create(
                        body.context_id, entity.text, entity.pii_type, strategy
                    )
        else:
            replacement_map = None

        final_text, mappings = _apply_replacements(
            body.text, entities_to_protect, resolved_mode, replacement_map, remove_types
        )

        pii_types = list({m.pii_type for m in mappings})
        entities_out = [
            EntityDetail(
                type=m.pii_type,
                value=m.original if body.include_entity_values else None,
                start=m.start,
                end=m.end,
                confidence=round(m.score, 4),
                replacement=m.token,
            )
            for m in mappings
        ]

        if not body.dry_run:
            _kp = key_provider if key_provider is not None else EnvKekKeyProvider(db, settings.encryption_key)
            repo = MappingRepository(db, _kp)
            # Removed entities have token="" — don't store (irreversible, no deanonymization possible)
            mappings_to_save = [m for m in mappings if m.token]
            await repo.save_many(mappings_to_save, body.context_id, body.context_type, tenant_id)

        ip_anon = getattr(request.app.state, "ip_anonymization_enabled", True)
        audit = AuditService(db, ip_anonymization=ip_anon)
        await audit.log(
            api_key_id=api_key.id,
            action="anonymize_dry_run" if body.dry_run else "anonymize",
            context_id=body.context_id,
            pii_types_found=pii_types,
            char_count=len(body.text),
            tenant_id=tenant_id,
            document_hash=_document_hash(body.text),
            ip=_client_ip(request),
        )

        policy_hash = policy["policy_hash"]
        try:
            await usage_service.record(
                api_key_id=api_key.id,
                request_id=request_id,
                policy_id=policy["policy_id"],
                policy_version=policy["policy_version"],
                policy_hash=policy_hash,
                chars_in=len(body.text),
                chars_out=len(final_text),
                entities_count=len(mappings),
                entity_types_summary=pii_types,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="ok",
                tenant_id=tenant_id,
            )
        except Exception:
            pass

        return AnonymizeResponse(
            anonymized_text=final_text,
            entity_count=len(mappings),
            pii_types_found=pii_types,
            entities=entities_out,
            mode=resolved_mode,
            policy=PolicyMetadata(
                id=policy["policy_id"],
                version=policy["policy_version"],
                hash=policy_hash,
            ),
            safe=True,
            dry_run=body.dry_run,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("anonymize failed for context_id=%s", request_id)
        try:
            await usage_service.record(
                api_key_id=api_key.id,
                request_id=request_id,
                policy_id=body.context_type,
                policy_version=policy.get("policy_version") if "policy" in locals() else None,
                policy_hash=None,
                chars_in=len(body.text),
                chars_out=0,
                entities_count=0,
                entity_types_summary=[],
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                status="error",
                error_code="PII_PROCESSING_FAILED",
                tenant_id=tenant_id,
            )
        except Exception:
            pass
        if settings.failure_mode == "partial":
            partial_response = await _build_partial_response(
                body=body,
                request=request,
                anonymizer=anonymizer,
                policy=policy if "policy" in locals() else None,
            )
            if partial_response is not None:
                try:
                    await usage_service.record(
                        api_key_id=api_key.id,
                        request_id=uuid.uuid4(),
                        policy_id=partial_response.policy.id,
                        policy_version=partial_response.policy.version,
                        policy_hash=partial_response.policy.hash,
                        chars_in=len(body.text),
                        chars_out=len(partial_response.anonymized_text),
                        entities_count=partial_response.entity_count,
                        entity_types_summary=partial_response.pii_types_found,
                        latency_ms=int((time.perf_counter() - started_at) * 1000),
                        status="partial",
                        error_code="PII_PROCESSING_PARTIAL",
                        tenant_id=tenant_id,
                    )
                except Exception:
                    pass
                return partial_response
        if settings.failure_mode == "open":
            return AnonymizeResponse(
                anonymized_text=body.text,
                entity_count=0,
                pii_types_found=[],
                entities=[],
                mode=body.mode or "tag",
                policy=PolicyMetadata(
                    id=body.context_type,
                    version=policy.get("policy_version") if "policy" in locals() else None,
                    hash=policy.get("policy_hash") if "policy" in locals() else None,
                ),
                safe=False,
                dry_run=body.dry_run,
                warnings=["Returned original text because fail-open mode is enabled."],
            )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "PII_PROCESSING_FAILED",
                "message": "The request was blocked because pii-protect could not safely complete detection.",
                "safe": False,
            },
        )
