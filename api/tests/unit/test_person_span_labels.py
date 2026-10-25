"""PERSON spans must stop at the name: no trailing punctuation or Italian field labels ("C.F.", "nato").

Raw spans below are the real layer outputs for the production report (openai/privacy-filter tags
" C.F." as its own PERSON fragment; the merger then glued it onto "Mario Rossi" -> "Mario Rossi, C.F.").
"""
from __future__ import annotations

import pytest

from app.anonymization.anonymizer import PiiAnonymizer, _snap_to_word_boundary
from app.detection.detector_registry import DetectorRegistry
from app.detection.entities import PiiEntity
from app.detection.entity_merger import EntityMerger
from app.routers._anonymize_logic import get_anonymizer
from tests.unit.test_documents import _post, env  # noqa: F401  (fixture reuse)

PROD_TEXT = "Contribuente Mario Rossi, C.F. RSSMRA80A01H501U"
# (layer, type, start, end, score, source) captured from the real models on PROD_TEXT
PROD_RAW = [
    ("presidio", "FISCAL_CODE", 31, 47, 1.0, ""), ("presidio", "PERSON", 13, 24, 0.85, ""),
    ("presidio", "PERSON", 26, 47, 0.85, ""), ("privacy_filter", "PERSON", 12, 24, 1.0, ""),
    ("privacy_filter", "PERSON", 25, 30, 0.989, ""), ("ai4privacy", "PERSON", 13, 18, 0.974, ""),
    ("ai4privacy", "PERSON", 19, 24, 0.898, ""), ("regex", "PERSON", 13, 24, 1.0, "regex"),
    ("regex", "FISCAL_CODE", 31, 47, 1.0, "regex"),
]


class ReplayDetector:
    """Why: reproduces the exact multi-layer raw spans without loading ML models.
    What: emits recorded spans (relative to PROD_TEXT) wherever PROD_TEXT occurs in the input.
    Test: detect(PROD_TEXT) returns len(PROD_RAW) entities for one detector holding all spans.
    """

    layer_name, priority = "replay", 0

    def is_available(self) -> bool:
        return True

    def detect(self, text: str, language: str = "it", cfg: dict | None = None) -> list[PiiEntity]:
        base = text.find(PROD_TEXT)
        if base < 0:
            return []
        return [PiiEntity(base + s, base + e, t, text[base + s:base + e], score, source)
                for _, t, s, e, score, source in PROD_RAW]


def _anonymizer() -> PiiAnonymizer:
    registry = DetectorRegistry()
    registry.register(ReplayDetector())
    return PiiAnonymizer(registry)


def test_production_example_detect_only_keeps_person_name_only():
    spans = [(e.pii_type, e.start, e.end, e.text) for e in _anonymizer().detect_only(PROD_TEXT, "c", "x").entities]
    assert spans == [("PERSON", 13, 24, "Mario Rossi"), ("FISCAL_CODE", 31, 47, "RSSMRA80A01H501U")]


def test_production_example_anonymize_keeps_label_in_clear():
    result = _anonymizer().anonymize(PROD_TEXT, "c", "x")
    assert result.anonymized_text == "Contribuente [PERSON_1], C.F. [FISCAL_CODE_1]"


def test_production_example_documents_preview(env):  # noqa: F811
    env.client.app.dependency_overrides[get_anonymizer] = _anonymizer
    r = _post(env, "preview", PROD_TEXT.encode(), filename="doc.txt", domain="tax_accounting")
    assert r.status_code == 200, r.text
    got = [(e["type"], e["start"], e["end"], r.json()["text"][e["start"]:e["end"]]) for e in r.json()["entities"]]
    assert got == [("PERSON", 13, 24, "Mario Rossi"), ("FISCAL_CODE", 31, 47, "RSSMRA80A01H501U")]


def _snap_person(text: str, span: str) -> PiiEntity | None:
    start = text.index(span)
    return _snap_to_word_boundary(text, PiiEntity(start, start + len(span), "PERSON", span, 0.9))


@pytest.mark.parametrize("suffix", [
    ", C.F.", " C.F.", ", CF", " cf", ", cod. fisc.", ", codice fiscale", ", P.IVA", " p.iva", ", partita iva",
    ", nato", ", nata", ", residente", " tel.", ", telefono", ", email", ", e-mail", " n.", ", matr.",
    ",", ";", ":", ".", " ,", ", ", " - ",
])
def test_trailing_labels_and_punctuation_are_trimmed(suffix):
    text = f"Contribuente Mario Rossi{suffix} XYZ"
    snapped = _snap_person(text, f"Mario Rossi{suffix}".rstrip())
    assert (snapped.start, snapped.text) == (text.index("Mario"), "Mario Rossi")


@pytest.mark.parametrize("label", ["C.F.", " C.F.", "nato", "tel.", ", P.IVA"])
def test_label_only_fragment_is_dropped(label):
    assert _snap_person(f"Mario Rossi, {label.strip(' ,')} 123", label) is None


@pytest.mark.parametrize("text,span,expected", [
    ("Il sig. Luca De Luca, nato a Roma", "sig. Luca De Luca, nato", "Luca De Luca"),
    ("Contribuente Anna Dalla Valle; P.IVA 01234567890", "Anna Dalla Valle; P.IVA", "Anna Dalla Valle"),
    ("Dott.ssa Giulia Verdi, cod. fisc. VRDGLI85M41F205X", "Dott.ssa Giulia Verdi, cod. fisc.", "Giulia Verdi"),
    ("Presente avv. Marco Della Torre.", "avv. Marco Della Torre.", "Marco Della Torre"),
    ("Firmato Natalia Rossi", "Natalia Rossi", "Natalia Rossi"),  # label-like prefix inside a word stays
    ("Firmato Mario Cfaro", "Mario Cfaro", "Mario Cfaro"),
])
def test_compound_names_stay_whole_and_titles_stay_out(text, span, expected):
    assert _snap_person(text, span).text == expected


def test_merger_clips_ml_span_instead_of_dropping_it_against_regex():
    text = "Mario Rossi, C.F. RSSMRA80A01H501U"
    ml = PiiEntity(0, 34, "PERSON", text, 0.9, "presidio")
    cf = PiiEntity(18, 34, "FISCAL_CODE", text[18:], 1.0, "regex")
    merged = EntityMerger().merge([ml, cf], text)
    assert [(e.pii_type, e.text) for e in merged] == [("PERSON", "Mario Rossi, C.F"), ("FISCAL_CODE", text[18:])]
    assert all(a.end <= b.start for a, b in zip(merged, merged[1:]))  # never overlapping
