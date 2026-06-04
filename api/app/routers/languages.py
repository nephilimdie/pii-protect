import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.settings_repository import SettingsRepository

router = APIRouter()
logger = logging.getLogger(__name__)

KNOWN_LANGUAGES: dict[str, dict] = {
    "it": {"name": "Italiano",    "model": "it_core_news_lg",  "size_mb": 550},
    "en": {"name": "English",     "model": "en_core_web_lg",   "size_mb": 560},
    "de": {"name": "Deutsch",     "model": "de_core_news_lg",  "size_mb": 550},
    "fr": {"name": "Français",    "model": "fr_core_news_lg",  "size_mb": 550},
    "es": {"name": "Español",     "model": "es_core_news_lg",  "size_mb": 550},
    "pt": {"name": "Português",   "model": "pt_core_news_lg",  "size_mb": 500},
    "nl": {"name": "Nederlands",  "model": "nl_core_news_lg",  "size_mb": 530},
}

# In-memory download status: code → {status, log}
_install_status: dict[str, dict] = {}


def _is_installed(model_name: str) -> bool:
    try:
        import spacy
        return spacy.util.is_package(model_name)
    except Exception:
        return False


class LanguageInfo(BaseModel):
    code: str
    name: str
    model: str
    size_mb: int
    installed: bool


class SettingsResponse(BaseModel):
    default_language: str


class InstallStatus(BaseModel):
    code: str
    status: str
    log: str


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    lang = await SettingsRepository(db).get("default_language", "it")
    return SettingsResponse(default_language=lang)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsResponse,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.default_language not in KNOWN_LANGUAGES:
        raise HTTPException(status_code=400, detail="unknown_language")
    if not _is_installed(KNOWN_LANGUAGES[body.default_language]["model"]):
        raise HTTPException(status_code=400, detail="language_not_installed")
    repo = SettingsRepository(db)
    await repo.set("default_language", body.default_language)
    request.app.state.default_language = body.default_language
    return SettingsResponse(default_language=body.default_language)


@router.get("/languages", response_model=list[LanguageInfo])
async def list_languages(api_key: ApiKey = Depends(require_admin)):
    return [
        LanguageInfo(
            code=code,
            installed=_is_installed(info["model"]),
            **info,
        )
        for code, info in KNOWN_LANGUAGES.items()
    ]


@router.post("/languages/{code}/install", response_model=InstallStatus)
async def install_language(
    code: str,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
):
    if code not in KNOWN_LANGUAGES:
        raise HTTPException(status_code=404, detail="unknown_language")
    if _is_installed(KNOWN_LANGUAGES[code]["model"]):
        return InstallStatus(code=code, status="already_installed", log="")
    if _install_status.get(code, {}).get("status") == "downloading":
        return InstallStatus(code=code, status="downloading", log=_install_status[code]["log"])

    _install_status[code] = {"status": "downloading", "log": ""}
    asyncio.create_task(_run_install(code, KNOWN_LANGUAGES[code]["model"], request))
    return InstallStatus(code=code, status="downloading", log="")


@router.get("/languages/{code}/status", response_model=InstallStatus)
async def install_status(code: str, api_key: ApiKey = Depends(require_admin)):
    if code not in KNOWN_LANGUAGES:
        raise HTTPException(status_code=404, detail="unknown_language")
    st = _install_status.get(code)
    if st is None:
        installed = _is_installed(KNOWN_LANGUAGES[code]["model"])
        return InstallStatus(code=code, status="installed" if installed else "not_installed", log="")
    return InstallStatus(code=code, status=st["status"], log=st.get("log", ""))


async def _run_install(code: str, model: str, request: Request) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "spacy", "download", model,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log_lines: list[str] = []
        assert proc.stdout
        async for line in proc.stdout:
            decoded = line.decode().rstrip()
            log_lines.append(decoded)
            _install_status[code]["log"] = "\n".join(log_lines[-20:])

        await proc.wait()
        if proc.returncode == 0:
            _install_status[code]["status"] = "installed"
            logger.info("spaCy model installed: %s", model)
            # Reload Presidio with the new language
            from app.detection.layers.presidio_layer import PresidioDetector
            installed_langs = [
                c for c, info in KNOWN_LANGUAGES.items()
                if _is_installed(info["model"])
            ]
            lang_models = [
                {"lang_code": c, "model_name": KNOWN_LANGUAGES[c]["model"]}
                for c in installed_langs
            ]
            PresidioDetector.reload(lang_models)
            request.app.state.installed_languages = installed_langs
        else:
            _install_status[code]["status"] = "error"
    except Exception as exc:
        _install_status[code] = {"status": "error", "log": str(exc)}
        logger.exception("Failed to install spaCy model %s", model)
