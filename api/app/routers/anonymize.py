import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.detection.detector_registry import DetectorRegistry
from app.anonymization.anonymizer import PiiAnonymizer
from app.mapping.repository import MappingRepository
from app.audit.audit_service import AuditService
from app.surrogates.policy_service import PolicyService
from app.surrogates.surrogate_service import SurrogateService
from app.surrogates.generators import language_to_locale
from app.detection.entities import MappingEntry

router = APIRouter()


class AnonymizeRequest(BaseModel):
    text: str
    context_id: str
    context_type: str
    language: str | None = None
    mode: str | None = None          # tag | surrogate — overrides context_type default
    policy: dict | None = None       # {"protect": [...], "keep": [...]} — inline override
    detection_mode: str = "permissive"  # permissive | strict


class EntityDetail(BaseModel):
    type: str
    value: str
    start: int
    end: int
    confidence: float
    replacement: str


class AnonymizeResponse(BaseModel):
    anonymized_text: str
    entity_count: int
    pii_types_found: list[str]
    entities: list[EntityDetail]
    mode: str


def get_registry(request: Request) -> DetectorRegistry:
    return request.app.state.registry


def get_denylist(request: Request) -> dict[str, dict]:
    return getattr(request.app.state, "denylist", {})


def get_anonymizer(
    registry: DetectorRegistry = Depends(get_registry),
    denylist: dict[str, dict] = Depends(get_denylist),
) -> PiiAnonymizer:
    return PiiAnonymizer(registry, denylist)


@router.post("/anonymize", response_model=AnonymizeResponse)
async def anonymize(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
):
    lang = body.language or getattr(request.app.state, "default_language", "it")
    locale = language_to_locale(lang)

    # Resolve policy and mode from context_type + inline overrides
    policy_svc = PolicyService(db)
    protect_types, keep_types, surrogate_types, resolved_mode = await policy_svc.resolve(
        context_type=body.context_type,
        inline_policy=body.policy,
        inline_mode=body.mode,
    )

    # Detection (CPU-bound — off-loop)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, anonymizer.detect_only, body.text, body.context_id, body.context_type, lang
        )
    except Exception:
        if body.detection_mode == "strict":
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="detection_layer_failure")
        raise

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

    # Persist mappings
    repo = MappingRepository(db)
    await repo.save_many(mappings, body.context_id, body.context_type)

    pii_types = list({m.pii_type for m in mappings})
    audit = AuditService(db)
    await audit.log(
        api_key_id=api_key.id,
        action="anonymize",
        context_id=body.context_id,
        pii_types_found=pii_types,
        char_count=len(body.text),
    )

    entities_out = [
        EntityDetail(
            type=m.pii_type,
            value=m.original,
            start=m.start,
            end=m.end,
            confidence=round(m.score, 4),
            replacement=m.token,
        )
        for m in mappings
    ]

    return AnonymizeResponse(
        anonymized_text=final_text,
        entity_count=len(mappings),
        pii_types_found=pii_types,
        entities=entities_out,
        mode=resolved_mode,
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
