import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import anonymize, deanonymize, health
from app.routers import identity as identity_router
from app.routers import reporting as reporting_router
from app.routers import regex_patterns as regex_patterns_router
from app.routers import denylist as denylist_router
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.detection.layers.regex_layer import ItalianRegexDetector
from app.detection.detector_provider import DetectorProvider
from app.detection.regex_pattern_repository import RegexPatternRepository
from app.detection.denylist_repository import DenylistRepository
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
    PresidioDetector.preload(settings.spacy_model)
    PrivacyFilterDetector.preload(settings.privacy_filter_model)
    Ai4PrivacyDetector.preload(settings.ai4privacy_model)

    async with AsyncSessionLocal() as db:
        patterns = await RegexPatternRepository(db).find_enabled()
        denylist_entries = await DenylistRepository(db).find_enabled()

    provider = DetectorProvider(settings, patterns)
    registry = provider.build()
    app.state.registry = registry
    app.state.regex_detector = registry.get_by_name("regex")

    denylist: dict[str, set[str]] = {}
    for e in denylist_entries:
        denylist.setdefault(e.pii_type, set()).add(e.value.lower())
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
