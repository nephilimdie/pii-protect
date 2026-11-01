"""Per-rule tests for the code-level Italian recognizers and the ML precision filter.

Why: every rule was added for a measured benchmark gap; these pin the positive case and the
look-alike it must not mask, so later tuning cannot silently trade one for the other.
"""
from __future__ import annotations

import pytest

from app.detection.entities import PiiEntity
from app.detection.recognizers import MAXIMUM, detect_contextual, precision_filter
from app.detection.recognizers.common import parse_date


def _found(text: str, level: str = "balanced") -> set[tuple[str, str]]:
    return {(e.pii_type, e.text) for e in detect_contextual(text, level)}


@pytest.mark.parametrize("text, expected", [
    ("Mario, nato in Venezia il 09/09/1985", {("CITY_BORN", "Venezia"), ("DATE_BORN", "09/09/1985")}),
    ("ROSSI LUCA n. a LECCE (LE) il 3/7/00", {("CITY_BORN", "LECCE"), ("DATE_BORN", "3/7/00")}),
    ("nata il 17 marzo 1951 a Bari", {("DATE_BORN", "17 marzo 1951"), ("CITY_BORN", "Bari")}),
    ("Data di nascita: 1951-03-17", {("DATE_BORN", "1951-03-17")}),
    ("Comune di nascita: San Donà di Piave", {("CITY_BORN", "San Donà di Piave")}),
])
def test_birth_data_after_cue(text, expected):
    assert expected <= _found(text)


def test_birth_date_matching_fiscal_code_without_cue():
    assert ("DATE_BORN", "01/01/1980") in _found("RSSMRA80A01H501U. Il 01/01/1980 è indicato in anagrafica.")


@pytest.mark.parametrize("text", ["udienza del 06.10.2020", "fattura del 12/03/2024 n. 55", "versione 1.2.3.4"])
def test_document_dates_and_versions_stay_clear(text):
    assert not {t for t, _ in _found(text)} & {"DATE_BORN", "IP_ADDRESS"}


@pytest.mark.parametrize("text, expected", [
    ("login da 10.1.2.3 alle 10:00", ("IP_ADDRESS", "10.1.2.3")),
    ("client 2001:db8::1 refused", ("IP_ADDRESS", "2001:db8::1")),
    ("R.G. n. 1234/2025", ("PRACTICE_ID", "1234/2025")),
    ("procedimento n. 77/2023 R.G.N.R.", ("PRACTICE_ID", "77/2023")),
    ("veicolo targato AB 123 CD", ("TARGA", "AB 123 CD")),
    ("targa ly388zm", ("TARGA", "ly388zm")),
    ("username: mario.rossi85", ("USERNAME", "mario.rossi85")),
    ("scrivimi su @marta_v", ("USERNAME", "marta_v")),
    ("sinistro n. RCA-2024-00817", ("POLICY_NUMBER", "RCA-2024-00817")),
    ("carta d'identità AX 1234567", ("IDENTITY_CARD", "AX 1234567")),
])
def test_identifiers(text, expected):
    assert expected in _found(text)


@pytest.mark.parametrize("text", ["L. 431/1998", "importo 191.799 euro", "login fallito", "art. 2043/1942"])
def test_identifier_look_alikes_stay_clear(text):
    assert _found(text) == set()


@pytest.mark.parametrize("text, expected", [
    ("Soggetto: COPPOLA DANIELA nato a LECCE", ("PERSON", "COPPOLA DANIELA")),
    ("Il sottoscritto Bianchi Giulio, residente", ("PERSON", "Bianchi Giulio")),
    ("Coniuge a carico: Anna De Luca", ("PERSON", "Anna De Luca")),
    ("customer marco ferri, cf RSSMRA80A01H501U", ("PERSON", "marco ferri")),
])
def test_person_after_cue(text, expected):
    assert expected in _found(text)


@pytest.mark.parametrize("text", ["Il Contratto Standard resta valido", "Oggetto: Ricorso Avverso Verbale",
                                  "Gentile Cliente, la contattiamo"])
def test_capitalised_phrases_without_name_stay_clear(text):
    assert not any(t == "PERSON" for t, _ in _found(text))


def test_key_aware_json_and_kv():
    found = _found('{"full_name":"Thi Lan Nguyen","ip":"76.182.195.80","request_id":"649a1f"} user=jdoe42 tax_code=x')
    assert {("PERSON", "Thi Lan Nguyen"), ("IP_ADDRESS", "76.182.195.80"), ("USERNAME", "jdoe42")} <= found
    assert not any(v == "649a1f" for _, v in found)


@pytest.mark.parametrize("text, pii_type", [
    ("CF: MNCPLA 72R43 A944X", "FISCAL_CODE"),
    ("cf rssmra80a01h501u", "FISCAL_CODE"),
    ("IBAN IT60 X054 2811 1010 0000 0123 456", "IBAN"),
    ("P.IVA 012 345 678 97", "VAT_NUMBER"),
    ("cell. 347-123-4567", "PHONE"),
])
def test_spaced_and_lowercase_values_with_checksum(text, pii_type):
    assert any(t == pii_type for t, _ in _found(text))


@pytest.mark.parametrize("text", ["Matricola: 004927", "Posizione INPS: 3600584292", "Prot. n. 0612345"])
def test_identifier_labels_are_not_phones(text):
    """Why: matricola / INPS numbers look like phones and were mislabelled PHONE (benchmark hr docs)."""
    assert not any(t == "PHONE" for t, _ in _found(text))


def test_ocr_damaged_fiscal_code_repaired_only_when_checksum_passes():
    assert any(t == "FISCAL_CODE" for t, _ in _found("codice RSSMRA8OAO1H5O1U"))  # O for 0
    assert not any(t == "FISCAL_CODE" for t, _ in _found("codice RSSMRA8OAO1H5O1A"))  # wrong check char


def test_parse_date_formats():
    assert parse_date("3/7/00").year == 2000
    assert parse_date("17 marzo 1951").month == 3
    assert parse_date("31/02/2020") is None


def _ml(text: str, pii_type: str, score: float = 0.9) -> PiiEntity:
    return PiiEntity(0, len(text), pii_type, text, score, "privacy_filter")


@pytest.mark.parametrize("entity", [
    _ml("Cordiali saluti", "PERSON"), _ml("PROCURA ALLE LITI", "PERSON"), _ml("R.G", "PERSON"),
    _ml("Lei", "PERSON"), _ml("431/1998", "ADDRESS"), _ml("191.799", "IP_ADDRESS"),
])
def test_precision_filter_drops_ml_look_alikes(entity):
    assert precision_filter([entity]) == []


def test_precision_filter_keeps_names_and_deterministic_spans():
    keep = [_ml("Mario Rossi", "PERSON"), PiiEntity(0, 3, "PERSON", "Lei", 1.0, "regex")]
    assert precision_filter(keep) == keep


def test_maximum_keeps_low_score_single_token_person():
    low = _ml("Gianluca", "PERSON", 0.75)
    assert precision_filter([low]) == []
    assert precision_filter([low], MAXIMUM) == [low]


def test_contextual_birth_date_replaces_same_span_generic_date():
    from app.detection.layers.regex_layer import ItalianRegexDetector
    from types import SimpleNamespace
    date = SimpleNamespace(pii_type="DATE", pattern=r"\b(\d{2}/\d{2}/\d{4})\b", flags="", capture_group=1)
    spans = {(e.pii_type, e.text) for e in ItalianRegexDetector([date]).detect("Marta, n. a Firenze il 13/04/1976.")}
    assert ("DATE_BORN", "13/04/1976") in spans and ("DATE", "13/04/1976") not in spans


def test_with_protection_level_defaults_to_balanced_and_rejects_unknown():
    from fastapi import HTTPException
    from app.routers._anonymize_logic import with_protection_level
    assert with_protection_level({"mode": "tag"}, None) == {"mode": "tag", "protection_level": "balanced"}
    assert with_protection_level({}, "maximum")["protection_level"] == "maximum"
    with pytest.raises(HTTPException) as err:
        with_protection_level({}, "max")
    assert err.value.status_code == 422


@pytest.mark.parametrize("text, level, expected", [
    ("residente in Corso Garibaldi 78/B, 35121 Padova (PD), a comparire", "balanced", "Corso Garibaldi 78/B, 35121 Padova (PD)"),
    ("Studio: CORSO DELLA REPUBBLICA 35 int. 9 - 47921 RIMINI RN\n", "balanced", "CORSO DELLA REPUBBLICA 35 int. 9 - 47921 RIMINI RN"),
    ("presso C.so Vittorio Emanuele II, 48 int. 1 - 35121 Padova. P.Q.M.", "balanced", "C.so Vittorio Emanuele II, 48 int. 1 - 35121 Padova"),
    ("Studio: via iv novembre 20/C ancona\n", "maximum", "via iv novembre 20/C ancona"),
    ("abita in Via Roma, vicino", "maximum", "Via Roma"),
])
def test_full_address_spans(text, level, expected):
    from app.detection.recognizers.address import detect_addresses
    assert expected in {e.text for e in detect_addresses(text, level) if e.pii_type == "ADDRESS"}


def test_street_without_number_only_at_maximum_and_cadastral_ref():
    from app.detection.recognizers.address import detect_addresses
    assert not detect_addresses("abita in Via Roma, vicino", "balanced")
    assert [e.text for e in detect_addresses("censita al N.C.E.U. al F. 51, P.lla 1309, sub 15. Il", "balanced")] == ["F. 51, P.lla 1309, sub 15"]
