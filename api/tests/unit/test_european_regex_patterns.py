from types import SimpleNamespace

from app.detection.layers.regex_layer import ItalianRegexDetector


PATTERNS = [
    ("DE_TAX_ID", r"(?i)\b(?:steuer[- ]?id|steueridentifikationsnummer)\s*[:#]?\s*(\d{11})\b"),
    ("FR_SIRET", r"(?i)\bsiret\s*[:#]?\s*(\d{14})\b"),
    ("FR_SIREN", r"(?i)\bsiren\s*[:#]?\s*(\d{9})\b"),
    ("ES_DNI_NIE", r"(?i)\b(?:dni|nie)\s*[:#]?\s*([xyz]?\d{7,8}[a-z])\b"),
    ("UK_NI_NUMBER", r"(?i)\b(?:national\s+insurance|ni\s+number)\s*[:#]?\s*([a-ceghj-pr-tw-z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[a-d])\b"),
    ("NL_BSN", r"(?i)\b(?:bsn|burgerservicenummer)\s*[:#]?\s*(\d{9})\b"),
]


def test_european_identifiers_require_explicit_labels():
    detector = ItalianRegexDetector([
        SimpleNamespace(pii_type=pii_type, pattern=pattern, flags="", capture_group=1)
        for pii_type, pattern in PATTERNS
    ])

    text = (
        "Steuer-ID: 12345678901; SIRET 12345678901234; SIREN: 123456789; "
        "DNI: 12345678Z; NI number: AB 12 34 56 C; BSN: 123456789"
    )
    found = {(entity.pii_type, entity.text) for entity in detector.detect(text, language="en")}

    assert {item[0] for item in found} == {item[0] for item in PATTERNS}
    assert "12345678901" in {item[1] for item in found}
    assert "AB 12 34 56 C" in {item[1] for item in found}
    assert detector.detect("Invoice 12345678901234 and order 123456789", language="en") == []
