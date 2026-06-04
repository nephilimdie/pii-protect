import logging
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

logger = logging.getLogger(__name__)

_LABEL_MAP: dict[str, str] = {
    "PERSON":            "PERSON",
    "EMAIL_ADDRESS":     "EMAIL",
    "PHONE_NUMBER":      "PHONE",
    "DATE_TIME":         "DATE",
    "IBAN_CODE":         "IBAN",
    "IT_FISCAL_CODE":    "FISCAL_CODE",
    "IT_DRIVER_LICENSE": "DRIVER_LICENSE",
    "IT_IDENTITY_CARD":  "IDENTITY_CARD",
    "IT_PASSPORT":       "PASSPORT",
    "CREDIT_CARD":       "CREDIT_CARD",
    "NRP":               "NRP",
    "URL":               "URL",
    # LOCATION excluded: spaCy produces too many false positives on generic words
}

_MIN_SCORE = 0.65

# Default lang → spaCy model mapping (extended when models are installed)
_DEFAULT_MODELS = [
    {"lang_code": "it", "model_name": "it_core_news_lg"},
]


class PresidioDetector(DetectorContract):
    _analyzer = None
    _supported_languages: list[str] = ["it"]

    def __init__(self) -> None:
        pass

    @property
    def layer_name(self) -> str:
        return "presidio"

    @property
    def priority(self) -> int:
        return 10

    def is_available(self) -> bool:
        return self._analyzer is not None

    @classmethod
    def preload(cls, lang_models: list[dict] | None = None) -> None:
        """lang_models: [{"lang_code": "it", "model_name": "it_core_news_lg"}, ...]"""
        models = lang_models or _DEFAULT_MODELS
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": models,
            })
            nlp_engine = provider.create_engine()
            langs = [m["lang_code"] for m in models]
            cls._analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=langs)
            cls._supported_languages = langs
            logger.info("Presidio loaded for languages: %s", langs)
        except Exception as exc:
            logger.warning("Presidio failed to load: %s", exc)

    @classmethod
    def reload(cls, lang_models: list[dict]) -> None:
        """Hot-reload after a new spaCy model is installed."""
        logger.info("Reloading Presidio with models: %s", [m["lang_code"] for m in lang_models])
        cls.preload(lang_models)

    def detect(self, text: str, language: str = "it") -> list[PiiEntity]:
        if self._analyzer is None:
            return []
        lang = language if language in self._supported_languages else self._supported_languages[0]
        try:
            results = self._analyzer.analyze(text=text, language=lang)
        except Exception as exc:
            logger.warning("Presidio analyze error: %s", exc)
            return []
        return [
            self._to_entity(r, text)
            for r in results
            if r.score >= _MIN_SCORE and r.entity_type in _LABEL_MAP
        ]

    def _to_entity(self, result, text: str) -> PiiEntity:
        pii_type = _LABEL_MAP.get(result.entity_type, result.entity_type)
        return PiiEntity(
            start=result.start,
            end=result.end,
            pii_type=pii_type,
            text=text[result.start:result.end],
            score=result.score,
        )
