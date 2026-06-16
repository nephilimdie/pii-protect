import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.tenant import get_tenant_id
from app.identity.models import ApiKey
from app.config import settings
from app.detection.detector_registry import DetectorRegistry
from app.anonymization.anonymizer import PiiAnonymizer
from app.mapping.repository import MappingRepository
from app.audit.audit_service import AuditService
from app.surrogates.policy_service import PolicyService
from app.surrogates.surrogate_service import SurrogateService
from app.surrogates.generators import language_to_locale
from app.detection.entities import MappingEntry
from app.usage.service import UsageService

router = APIRouter()


class AnonymizeRequest(BaseModel):
    text: str
    context_id: str
    context_type: str
    language: str | None = None
    mode: str | None = None          # tag | surrogate — overrides context_type default
    policy: dict | None = None       # {"protect": [...], "keep": [...]} — inline override
    detection_mode: str = "permissive"  # permissive | strict
    include_entity_values: bool = False
    dry_run: bool = False


class PolicyMetadata(BaseModel):
    id: str | None = None
    version: str | None = None
    hash: str | None = None


class EntityDetail(BaseModel):
    type: str
    start: int
    end: int
    confidence: float
    replacement: str
    value: str | None = None


class AnonymizeResponse(BaseModel):
    anonymized_text: str
    entity_count: int
    pii_types_found: list[str]
    entities: list[EntityDetail]
    mode: str
    policy: PolicyMetadata
    safe: bool = True
    dry_run: bool = False
    warnings: list[str] | None = None


class BatchItemResult(BaseModel):
    id: str
    status: str
    output: str | None = None
    error_code: str | None = None
    warnings: list[str] | None = None


class BatchItemRequest(BaseModel):
    id: str
    text: str
    context_type: str | None = None
    language: str | None = None
    mode: str | None = None
    policy: dict | None = None
    dry_run: bool | None = None


class BatchAnonymizeRequest(BaseModel):
    items: list[BatchItemRequest]
    context_type: str = "default"
    language: str | None = None
    mode: str | None = None
    policy: dict | None = None
    dry_run: bool = True


class BatchAnonymizeResponse(BaseModel):
    items: list[BatchItemResult]


def get_registry(request: Request) -> DetectorRegistry:
    return request.app.state.registry


def get_denylist(request: Request) -> dict[str, dict]:
    return getattr(request.app.state, "denylist", {})


def get_anonymizer(
    registry: DetectorRegistry = Depends(get_registry),
    denylist: dict[str, dict] = Depends(get_denylist),
) -> PiiAnonymizer:
    return PiiAnonymizer(registry, denylist)


@router.post("/anonymize", response_model=AnonymizeResponse, response_model_exclude_none=True)
async def anonymize(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
):
    return await _process_anonymization(body, request, api_key, db, anonymizer, tenant_id)


@router.post("/anonymize/batch", response_model=BatchAnonymizeResponse)
async def anonymize_batch(
    body: BatchAnonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
):
    if len(body.items) > settings.batch_max_items:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BATCH_LIMIT_EXCEEDED",
                "message": f"Batch requests are limited to {settings.batch_max_items} items.",
            },
        )

    results: list[BatchItemResult] = []
    for item in body.items:
        try:
            item_body = AnonymizeRequest.model_validate({
                "text": item.text,
                "context_id": item.id,
                "context_type": item.context_type or body.context_type,
                "language": item.language or body.language,
                "mode": item.mode or body.mode,
                "policy": item.policy or body.policy,
                "dry_run": body.dry_run if item.dry_run is None else item.dry_run,
            })
            response = await _process_anonymization(item_body, request, api_key, db, anonymizer, tenant_id)
            results.append(
                BatchItemResult(
                    id=item.id,
                    status="processed",
                    output=response.anonymized_text,
                    warnings=response.warnings,
                )
            )
        except HTTPException as exc:
            results.append(BatchItemResult(id=item.id, status="failed", error_code=str(exc.detail)))
    return BatchAnonymizeResponse(items=results)


async def _process_anonymization(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey,
    db: AsyncSession,
    anonymizer: PiiAnonymizer,
    tenant_id: str | None = None,
) -> AnonymizeResponse:
    lang = body.language or getattr(request.app.state, "default_language", "it")
    locale = language_to_locale(lang)
    request_id = uuid.uuid4()
    started_at = time.perf_counter()
    usage_service = UsageService(db)

    try:
        await usage_service.ensure_within_limits(api_key, len(body.text))

        # Resolve policy and mode from context_type + inline overrides
        policy_svc = PolicyService(db, tenant_id=tenant_id)
        policy = await policy_svc.resolve(
            context_type=body.context_type,
            inline_policy=body.policy,
            inline_mode=body.mode,
        )
        protect_types = policy["protect_types"]
        keep_types = policy["keep_types"]
        surrogate_types = policy["surrogate_types"]
        resolved_mode = policy["mode"]

        if body.include_entity_values and api_key.role != "admin":
            raise HTTPException(status_code=403, detail="insufficient_role")

        # Detection (CPU-bound — off-loop)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, anonymizer.detect_only, body.text, body.context_id, body.context_type, lang
        )

        # Filter entities by policy
        entities_to_protect = []
        for entity in result.entities:
            if entity.pii_type in keep_types:
                continue  # keep as-is in text
            if protect_types is not None and entity.pii_type not in protect_types and entity.pii_type not in surrogate_types:
                continue  # not in any protect/surrogate list → skip
            entities_to_protect.append(entity)

        # Build replacements
        # surrogate_types are always fake regardless of context-level mode
        needs_surrogate = resolved_mode == "surrogate" or bool(surrogate_types)
        if needs_surrogate:
            surrogate_svc = SurrogateService(db, locale=locale)
            replacement_map: dict[str, str] = {}
            for entity in entities_to_protect:
                # per-type override: surrogate_types always get fake value; others follow mode
                if resolved_mode != "surrogate" and entity.pii_type not in surrogate_types:
                    continue  # tag mode, not a per-type surrogate → skip (handled as tag below)
                key = entity.text.lower().strip()
                if key not in replacement_map:
                    strategy = await policy_svc.get_faker_strategy(entity.pii_type)
                    replacement_map[key] = await surrogate_svc.get_or_create(
                        body.context_id, entity.text, entity.pii_type, strategy
                    )
        else:
            replacement_map = None  # tag mode handled in _apply_replacements

        # Apply replacements to text
        final_text, mappings = _apply_replacements(
            body.text, entities_to_protect, resolved_mode, replacement_map
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
            # Persist mappings
            repo = MappingRepository(db)
            await repo.save_many(mappings, body.context_id, body.context_type)

        audit = AuditService(db)
        await audit.log(
            api_key_id=api_key.id,
            action="anonymize_dry_run" if body.dry_run else "anonymize",
            context_id=body.context_id,
            pii_types_found=pii_types,
            char_count=len(body.text),
            tenant_id=tenant_id,
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


async def _build_partial_response(
    body: AnonymizeRequest,
    request: Request,
    anonymizer: PiiAnonymizer,
    policy: dict | None,
) -> AnonymizeResponse | None:
    try:
        lang = body.language or getattr(request.app.state, "default_language", "it")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, anonymizer.detect_only, body.text, body.context_id, body.context_type, lang
        )
        final_text, mappings = _apply_replacements(body.text, result.entities, "tag", None)
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


def _apply_replacements(
    text: str,
    entities: list,
    mode: str,
    replacement_map: dict[str, str] | None,
) -> tuple[str, list[MappingEntry]]:
    from app.detection.token_generator import TokenGenerator
    generator = TokenGenerator()
    stable_map: dict[str, str] = {}

    for entity in entities:
        key = entity.text.lower().strip()
        if key in stable_map:
            continue
        if mode == "surrogate" and replacement_map:
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
