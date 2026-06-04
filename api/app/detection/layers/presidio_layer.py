import logging
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

logger = logging.getLogger(__name__)

_LABEL_MAP: dict[str, str] = {
    "PERSON":           "PERSON",
    "EMAIL_ADDRESS":    "EMAIL",
    "PHONE_NUMBER":     "PHONE",
    "DATE_TIME":        "DATE",
    "IBAN_CODE":        "IBAN",
    "IT_FISCAL_CODE":   "FISCAL_CODE",
    "IT_DRIVER_LICENSE":"DRIVER_LICENSE",
    "IT_IDENTITY_CARD": "IDENTITY_CARD",
    "IT_PASSPORT":      "PASSPORT",
    "CREDIT_CARD":      "CREDIT_CARD",
    "NRP":              "SECRET",
    "URL":              "SECRET",
    # LOCATION excluded: spaCy it_core_news_lg produces too many false positives
}


class PresidioDetector(DetectorContract):
    _analyzer = None

    def __init__(self, model: str = "it_core_news_lg") -> None:
        self._model = model

    @property
    def layer_name(self) -> str:
        return "presidio"

    @property
    def priority(self) -> int:
        return 10

    def is_available(self) -> bool:
        return self._analyzer is not None

    @classmethod
    def preload(cls, model: str = "it_core_news_lg") -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "it", "model_name": model}],
            })
            nlp_engine = provider.create_engine()
            cls._analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["it"])
            logger.info("Presidio analyzer loaded")
        except Exception as exc:
            logger.warning("Presidio failed to load: %s", exc)

    _MIN_SCORE = 0.65

    def detect(self, text: str) -> list[PiiEntity]:
        if self._analyzer is None:
            return []
        try:
            results = self._analyzer.analyze(text=text, language="it")
        except Exception as exc:
            logger.warning("Presidio analyze error: %s", exc)
            return []
        return [
            self._to_entity(r, text)
            for r in results
            if r.score >= self._MIN_SCORE and r.entity_type in _LABEL_MAP
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
