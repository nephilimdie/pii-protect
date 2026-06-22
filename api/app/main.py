from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1, send_default_pii=False)
    except ImportError:
        pass

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware

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
from app.routers import scoped_config as scoped_config_router
from app.routers import retention as retention_router
from app.routers import layer_settings as layer_settings_router
from app.routers import plugins_router
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

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def _layer_enabled(name: str) -> bool:
    return bool(settings.detection_layers.get(name, {}).get("enabled", True))


def _detection_layers_raw() -> list[dict]:
    meta = {
        "regex": ("Regex", "Deterministic database and built-in regular-expression detection"),
        "presidio": ("Presidio/spaCy", "NER and recognizer-based detection through Presidio and spaCy"),
        "privacy_filter": ("Privacy Filter", "ONNX privacy-filter model for broad PII detection"),
        "ai4privacy": ("AI4Privacy", "Transformer layer with wider PII category coverage"),
    }
    return [
        {
            "code": code,
            "display_name": label,
            "description": description,
            "enabled": _layer_enabled(code),
        }
        for code, (label, description) in meta.items()
    ]


class _JsonFormatter(logging.Formatter):
    _EXTRA_FIELDS = ("request_id", "tenant_id", "status")

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for field in self._EXTRA_FIELDS:
            val = getattr(record, field, None)
            if val is not None:
                payload[field] = val
        return json.dumps(payload, ensure_ascii=False)


_json_handler = logging.StreamHandler()
_json_handler.setFormatter(_JsonFormatter())
logging.root.handlers = [_json_handler]


_MAX_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(6 * 1024 * 1024)))  # 6 MB default


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        cl = request.headers.get("content-length")
        if cl and int(cl) > _MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": "request_body_too_large", "max_bytes": _MAX_BODY_BYTES},
                status_code=413,
            )
        return await call_next(request)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Request-Id"] = request_id
        tenant_id = request.headers.get("x-pii-tenant-id") or getattr(request.state, "tenant_id", None)
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id, "tenant_id": tenant_id, "status": response.status_code},
        )
        return response


async def _run_gdpr_cleanup() -> None:
    """One pass of GDPR cleanup. Each table uses an independent session so a failure in one
    does not roll back the others — partial cleanup is better than no cleanup."""
    from app.mapping.repository import MappingRepository as _MR
    from app.audit.audit_service import AuditService as _AS
    from app.usage.models import UsageEvent as _UE
    from app.settings_repository import SettingsRepository as _SR
    from sqlalchemy import delete as _delete

    async with AsyncSessionLocal() as db:
        cfg = await _SR(db).all()

    mapping_ttl = int(cfg.get("mapping_ttl_days",     "30"))
    audit_ttl   = int(cfg.get("audit_log_ttl_days",   "365"))
    usage_ttl   = int(cfg.get("usage_event_ttl_days", "395"))

    async with AsyncSessionLocal() as db:
        m_del = await _MR(db).delete_expired(mapping_ttl)

    async with AsyncSessionLocal() as db:
        a_del = await _AS(db).delete_expired(audit_ttl)

    async with AsyncSessionLocal() as db:
        cutoff = datetime.utcnow() - timedelta(days=usage_ttl)
        u_res  = await db.execute(_delete(_UE).where(_UE.created_at < cutoff))
        await db.commit()
        u_del  = u_res.rowcount

    logger.info(
        "GDPR cleanup done: mappings=%d audit=%d usage=%d",
        m_del, a_del, u_del,
    )


async def _nightly_cleanup_loop() -> None:
    """Art. 5 §1e GDPR — cleanup runs immediately at startup, then every 24 h."""
    try:
        await _run_gdpr_cleanup()
    except Exception:
        logger.exception("GDPR startup cleanup failed")

    while True:
        await asyncio.sleep(24 * 3600)
        try:
            await _run_gdpr_cleanup()
        except Exception:
            logger.exception("GDPR nightly cleanup failed")


async def _ensure_admin_key() -> None:
    import hashlib
    from sqlalchemy import update
    from app.identity.models import ApiKey

    key_hash = hashlib.sha256(settings.admin_initial_key.encode()).hexdigest()
    async with AsyncSessionLocal() as db:
        stmt = update(ApiKey).where(ApiKey.name == "admin").values(key_hash=key_hash)
        result = await db.execute(stmt)
        await db.commit()
        if result.rowcount > 0:
            logger.info("Admin initial key synchronized from environment")
            return

    async with AsyncSessionLocal() as db:
        service = ApiKeyService(db)
        await service.create("admin", "admin")
        stmt = update(ApiKey).where(ApiKey.name == "admin").values(key_hash=key_hash)
        await db.execute(stmt)
        await db.commit()
    logger.info("Admin initial key created from environment")


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
    if _layer_enabled("presidio"):
        logger.info("Preloading Presidio detector")
        PresidioDetector.preload(lang_models)
    else:
        logger.info("Skipping Presidio detector preload because layer is disabled")
    app.state.installed_languages = [m["lang_code"] for m in lang_models]

    if _layer_enabled("privacy_filter"):
        logger.info("Preloading PrivacyFilter detector")
        PrivacyFilterDetector.preload(settings.privacy_filter_model)
    else:
        logger.info("Skipping PrivacyFilter detector preload because layer is disabled")

    if _layer_enabled("ai4privacy"):
        logger.info("Preloading Ai4Privacy detector")
        Ai4PrivacyDetector.preload(settings.ai4privacy_model)
    else:
        logger.info("Skipping Ai4Privacy detector preload because layer is disabled")

    async with AsyncSessionLocal() as db:
        patterns = await RegexPatternRepository(db).find_enabled()
        denylist_entries = await DenylistRepository(db).find_enabled()
        default_lang = await SettingsRepository(db).get("default_language", "it")
        ctx_entries = await PresidioContextRepository(db).find_enabled()
        reclass_rules = await ReclassificationRepository(db).find_enabled()
    set_reclassify_rules(reclass_rules)
    app.state.default_language = default_lang
    app.state.detection_layers_raw = _detection_layers_raw()

    context_map: dict[str, list[str]] = {}
    for e in ctx_entries:
        context_map.setdefault(e["entity_type"], []).append(e["word"])
    app.state.presidio_context = context_map
    app.state.presidio_context_raw = [
        {
            "id": str(e["id"]),
            "entity_type": e["entity_type"],
            "word": e["word"],
            "description": e.get("description"),
            "enabled": e.get("enabled", True),
        }
        for e in ctx_entries
    ]
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

    # Raw lists stored for CloudScopedDetectionConfigResolver to apply tenant overrides on top
    app.state.denylist_raw = [
        {"id": str(e.id), "pii_type": e.pii_type, "value": e.value,
         "match_type": e.match_type, "enabled": e.enabled}
        for e in denylist_entries
    ]
    app.state.regex_patterns_raw = [
        {"id": str(p.id), "pii_type": p.pii_type, "pattern": p.pattern,
         "flags": p.flags, "capture_group": p.capture_group,
         "description": p.description, "enabled": p.enabled}
        for p in patterns
    ]
    app.state.reclassification_rules_raw = reclass_rules

    await _ensure_admin_key()

    # Load retention settings into app state for zero-overhead access per request
    async with AsyncSessionLocal() as db:
        from app.settings_repository import SettingsRepository as _SR
        _s = await _SR(db).all()
        app.state.ip_anonymization_enabled = _s.get("ip_anonymization_enabled", "true") == "true"

    _cleanup_task = asyncio.create_task(_nightly_cleanup_loop())

    yield

    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="pii-protect", version="1.0.0", lifespan=lifespan)

# ── Middleware ───────────────────────────────────────────────────────────────
_allowed_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()] \
    if hasattr(settings, "cors_allowed_origins") and settings.cors_allowed_origins else []

_is_production = os.getenv("APP_ENV", "development").lower() in ("production", "prod")
if _is_production and not _allowed_origins:
    raise RuntimeError(
        "PII_CORS_ALLOWED_ORIGINS must be set to explicit origins in production. "
        "CORS wildcard with credentials is rejected by all browsers."
    )

_placeholders = ("CHANGE_ME", "changeme", "your-", "example")
if _is_production:
    for _field, _val in [
        ("ENCRYPTION_KEY", settings.encryption_key),
        ("ADMIN_INITIAL_KEY", settings.admin_initial_key),
    ]:
        if not _val or any(p in _val for p in _placeholders):
            raise RuntimeError(
                f"{_field} contains a placeholder or is empty — set a real value before deploying to production."
            )

if settings.multitenancy_enabled and settings.accept_tenant_header and not settings.internal_api_key:
    logger.warning(
        "SECURITY: multitenancy_enabled=true + accept_tenant_header=true but "
        "PII_INTERNAL_API_KEY is not set. Any caller with a global API key can "
        "pass X-Pii-Tenant-Id. Set PII_INTERNAL_API_KEY to restrict access to "
        "the cloud layer only."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["*"],
    allow_credentials=bool(_allowed_origins),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(MaxBodySizeMiddleware)


@app.middleware("http")
async def tenant_guard_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)

    if not settings.multitenancy_enabled:
        headers = MutableHeaders(scope=request.scope)
        headers.pop("x-pii-tenant-id", None)
    else:
        # Internal API key check: must come BEFORE tenant-id handling
        if settings.internal_api_key:
            incoming_key = request.headers.get("x-api-key", "")
            if incoming_key != settings.internal_api_key:
                return JSONResponse({"detail": "internal_key_required"}, status_code=403)

        if settings.accept_tenant_header:
            pass
        else:
            if request.headers.get("x-pii-tenant-id"):
                return JSONResponse({"detail": "tenant_header_not_accepted"}, status_code=403)
    return await call_next(request)

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
app.include_router(scoped_config_router.router, prefix="/v1/admin")
app.include_router(plugins_router.router, prefix="/v1/admin")
app.include_router(retention_router.router, prefix="/v1/admin")
app.include_router(layer_settings_router.router, prefix="/v1/admin")
