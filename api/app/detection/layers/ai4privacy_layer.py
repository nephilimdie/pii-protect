import logging
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "Isotonic/distilbert_finetuned_ai4privacy_v2"

_LABEL_MAP: dict[str, str | None] = {
    "FIRSTNAME":          "PERSON",
    "LASTNAME":           "PERSON",
    "MIDDLENAME":         "PERSON",
    "PREFIX":             "PERSON",
    "EMAIL":              "EMAIL",
    "PHONENUMBER":        "PHONE",
    "PHONEIMEI":          "PHONE",
    "PASSWORD":           "SECRET",
    "USERNAME":           "SECRET",
    "ACCOUNTNUMBER":      "SECRET",
    "ACCOUNTNAME":        "SECRET",
    "CREDITCARDNUMBER":   "CREDIT_CARD",
    "CREDITCARDCVV":      "CVV",
    "MASKEDNUMBER":       "SECRET",
    "SSN":                "SECRET",
    "PIN":                "PIN",
    "IBAN":               "IBAN",
    "BIC":                "SECRET",
    "BITCOINADDRESS":     "SECRET",
    "ETHEREUMADDRESS":    "SECRET",
    "LITECOINADDRESS":    "SECRET",
    "IPV4":               "IP_ADDRESS",
    "IPV6":               "IP_ADDRESS",
    "IP":                 "IP_ADDRESS",
    "MAC":                "MAC_ADDRESS",
    "URL":                "SECRET",
    "USERAGENT":          "SECRET",
    "VEHICLEVRM":         "TARGA",
    "VEHICLEVIN":         "SECRET",
    "STREET":             "ADDRESS",
    "BUILDINGNUMBER":     "ADDRESS",
    "SECONDARYADDRESS":   "ADDRESS",
    "CITY":               "ADDRESS",
    "STATE":              "ADDRESS",
    "COUNTY":             "ADDRESS",
    "ZIPCODE":            "ADDRESS",
    "NEARBYGPSCOORDINATE": "ADDRESS",
    "DATE":               "DATE",
    "DOB":                "DATE",
    # skip noise categories
    "TIME":               None,
    "AGE":                None,
    "GENDER":             None,
    "SEX":                None,
    "HEIGHT":             None,
    "EYECOLOR":           None,
    "JOBTITLE":           None,
    "JOBAREA":            None,
    "JOBTYPE":            None,
    "COMPANYNAME":        None,
    "ORDINALDIRECTION":   None,
    "CURRENCY":           None,
    "CURRENCYCODE":       None,
    "CURRENCYNAME":       None,
    "CURRENCYSYMBOL":     None,
    "CREDITCARDISSUER":   None,
    "AMOUNT":             None,
}

_MIN_SCORE = 0.70


class Ai4PrivacyDetector(DetectorContract):
    _pipeline = None

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    @property
    def layer_name(self) -> str:
        return "ai4privacy"

    @property
    def priority(self) -> int:
        return 25

    def is_available(self) -> bool:
        return self._pipeline is not None

    @classmethod
    def preload(cls, model: str = _DEFAULT_MODEL) -> None:
        try:
            from transformers import pipeline as hf_pipeline
            cls._pipeline = hf_pipeline(
                "token-classification",
                model=model,
                aggregation_strategy="simple",
            )
            logger.info("Ai4Privacy model loaded: %s", model)
        except Exception as exc:
            logger.warning("Ai4Privacy model unavailable: %s", exc)

    def detect(self, text: str) -> list[PiiEntity]:
        if self._pipeline is None:
            return []
        try:
            results = self._pipeline(text)
        except Exception as exc:
            logger.warning("Ai4Privacy inference error: %s", exc)
            return []

        entities = []
        for item in results:
            score = float(item["score"])
            if score < _MIN_SCORE:
                continue
            pii_type = _LABEL_MAP.get(item.get("entity_group", ""), "SECRET")
            if pii_type is None:
                continue
            entities.append(PiiEntity(
                start=item["start"],
                end=item["end"],
                pii_type=pii_type,
                text=item["word"],
                score=score,
            ))
        return entities
