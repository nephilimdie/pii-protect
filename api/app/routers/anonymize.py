import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import require_service
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
    dry_run: bool = False


class BatchItemResult(BaseModel):
    id: str
    status: str
    output: str | None = None
    error_code: str | None = None


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
):
    return await _process_anonymization(body, request, api_key, db, anonymizer)


@router.post("/anonymize/batch", response_model=BatchAnonymizeResponse)
async def anonymize_batch(
    body: dict,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
):
    items = body.get("items", [])
    results: list[BatchItemResult] = []
    default_context_type = body.get("context_type", "default")
    default_language = body.get("language")
    default_mode = body.get("mode")
    default_policy = body.get("policy") if isinstance(body.get("policy"), dict) else None
    default_dry_run = body.get("dry_run", True)
    for item in items:
        try:
            item_body = AnonymizeRequest.model_validate({
                "text": item.get("text", ""),
                "context_id": item.get("id", ""),
                "context_type": item.get("context_type", default_context_type),
                "language": item.get("language", default_language),
                "mode": item.get("mode", default_mode),
                "policy": item.get("policy", default_policy),
                "dry_run": item.get("dry_run", default_dry_run),
            })
            response = await _process_anonymization(item_body, request, api_key, db, anonymizer)
            results.append(BatchItemResult(id=item.get("id", ""), status="processed", output=response.anonymized_text))
        except HTTPException as exc:
            results.append(BatchItemResult(id=item.get("id", ""), status="failed", error_code=str(exc.detail)))
    return BatchAnonymizeResponse(items=results)


async def _process_anonymization(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey,
    db: AsyncSession,
    anonymizer: PiiAnonymizer,
) -> AnonymizeResponse:
    lang = body.language or getattr(request.app.state, "default_language", "it")
    locale = language_to_locale(lang)
    request_id = uuid.uuid4()
    started_at = time.perf_counter()
    usage_service = UsageService(db)

    try:
        await usage_service.ensure_within_limits(api_key, len(body.text))

        # Resolve policy and mode from context_type + inline overrides
        policy_svc = PolicyService(db)
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
        if settings.failure_mode == "open":
            return AnonymizeResponse(
                anonymized_text=body.text,
                entity_count=0,
                pii_types_found=[],
                entities=[],
                mode=body.mode or "tag",
                dry_run=body.dry_run,
            )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "PII_PROCESSING_FAILED",
                "message": "The request was blocked because pii-protect could not safely complete detection.",
                "safe": False,
            },
        )


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
