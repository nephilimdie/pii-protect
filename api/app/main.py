import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import anonymize, deanonymize, health
from app.routers import identity as identity_router
from app.routers import reporting as reporting_router
from app.routers import regex_patterns as regex_patterns_router
from app.routers import denylist as denylist_router
from app.routers import languages as languages_router
from app.routers import presidio_context as presidio_context_router
from app.routers import reclassification as reclassification_router
from app.routers import pii_types_router
from app.routers import domain_policies_router
from app.routers import context_types_router
from app.detection.layers.presidio_layer import PresidioDetector
from app.settings_repository import SettingsRepository
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.detection.layers.regex_layer import ItalianRegexDetector
from app.detection.detector_provider import DetectorProvider
from app.detection.regex_pattern_repository import RegexPatternRepository
from app.detection.denylist_repository import DenylistRepository
from app.detection.presidio_context_repository import PresidioContextRepository
from app.detection.reclassification_repository import ReclassificationRepository
from app.anonymization.anonymizer import set_reclassify_rules
from app.database import AsyncSessionLocal
from app.identity.api_key_service import ApiKeyService
from app.config import settings

logger = logging.getLogger(__name__)


async def _ensure_admin_key() -> None:
    async with AsyncSessionLocal() as db:
        service = ApiKeyService(db)
        count = await service.count()
        if count > 0:
            return
        _, plain_key = await service.create("admin", "admin")
    async with AsyncSessionLocal() as db:
        import hashlib
        from sqlalchemy import update
        from app.identity.models import ApiKey
        key_hash = hashlib.sha256(settings.admin_initial_key.encode()).hexdigest()
        stmt = update(ApiKey).where(ApiKey.name == "admin").values(key_hash=key_hash)
        await db.execute(stmt)
        await db.commit()
    logger.info("Admin initial key configured from environment")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load Presidio with all installed spaCy models
    from app.routers.languages import KNOWN_LANGUAGES, _is_installed
    lang_models = [
        {"lang_code": code, "model_name": info["model"]}
        for code, info in KNOWN_LANGUAGES.items()
        if _is_installed(info["model"])
    ]
    if not lang_models:
        lang_models = [{"lang_code": "it", "model_name": settings.spacy_model}]
    PresidioDetector.preload(lang_models)
    app.state.installed_languages = [m["lang_code"] for m in lang_models]

    PrivacyFilterDetector.preload(settings.privacy_filter_model)
    Ai4PrivacyDetector.preload(settings.ai4privacy_model)

    async with AsyncSessionLocal() as db:
        patterns = await RegexPatternRepository(db).find_enabled()
        denylist_entries = await DenylistRepository(db).find_enabled()
        default_lang = await SettingsRepository(db).get("default_language", "it")
        ctx_entries = await PresidioContextRepository(db).find_enabled()
        reclass_rules = await ReclassificationRepository(db).find_enabled()
    set_reclassify_rules(reclass_rules)
    app.state.default_language = default_lang

    context_map: dict[str, list[str]] = {}
    for e in ctx_entries:
        context_map.setdefault(e["entity_type"], []).append(e["word"])
    app.state.presidio_context = context_map
    PresidioDetector.set_context(context_map)

    provider = DetectorProvider(settings, patterns)
    registry = provider.build()
    app.state.registry = registry
    app.state.regex_detector = registry.get_by_name("regex")

    denylist: dict[str, dict] = {}
    for e in denylist_entries:
        bucket = denylist.setdefault(e.pii_type, {"exact": set(), "contains": []})
        if e.match_type == "contains":
            bucket["contains"].append(e.value.lower())
        else:
            bucket["exact"].add(e.value.lower())
    app.state.denylist = denylist

    await _ensure_admin_key()
    yield


app = FastAPI(title="pii-protect", version="1.0.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(identity_router.router, prefix="/v1/auth")
app.include_router(anonymize.router, prefix="/v1")
app.include_router(deanonymize.router, prefix="/v1")
app.include_router(reporting_router.router, prefix="/v1/admin")
app.include_router(regex_patterns_router.router, prefix="/v1/admin")
app.include_router(denylist_router.router, prefix="/v1/admin")
app.include_router(languages_router.router, prefix="/v1/admin")
app.include_router(presidio_context_router.router, prefix="/v1/admin")
app.include_router(reclassification_router.router, prefix="/v1/admin")
app.include_router(pii_types_router.router, prefix="/v1/admin")
app.include_router(domain_policies_router.router, prefix="/v1/admin")
app.include_router(context_types_router.router, prefix="/v1/admin")
