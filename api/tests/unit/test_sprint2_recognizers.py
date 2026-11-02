import pytest
from dataclasses import replace

from app.detection.recognizers import detect_contextual
from app.detection.recognizers.common import parse_date
from app.detection.recognizers.network import detect_network
from app.detection.recognizers.tabular import detect_tabular
from app.detection.recognizers.precision import precision_filter
from app.detection.recognizers.common import entity
from app.detection.entity_merger import EntityMerger


@pytest.mark.parametrize("value", ["mario[at]example[dot]it", "mario (at) example.it", "mario%40example.it"])
def test_obfuscated_email_preserves_original_span(value):
    text = "Contatto: " + value + "; grazie."
    assert any(e.pii_type == "EMAIL" and e.text == value for e in detect_network(text))


@pytest.mark.parametrize("value", ["2001:db8::1", "::1", "fe80::1234:abcd"])
def test_ipv6_requires_valid_address(value):
    assert any(e.text == value for e in detect_network("IP " + value))
    assert not detect_network("IP 2001:xyz::1 o ora 12:30:40")


@pytest.mark.parametrize("value", ["16-GIU-1979", "16 giu 1979", "16/giu/79"])
def test_abbreviated_birth_date(value):
    assert parse_date(value).month == 6
    assert any(e.pii_type == "DATE_BORN" and e.text == value for e in detect_contextual("Data di nascita: " + value))
    assert not any(e.pii_type == "DATE_BORN" for e in detect_contextual("Battaglia del " + value))


def test_invalid_month_or_date_is_not_accepted():
    assert parse_date("16 giusto 1979") is None
    assert parse_date("31 feb 1979") is None


def test_split_cf_checksum():
    good = "RSS MRA 80A01 H501U"
    assert any(e.pii_type == "FISCAL_CODE" and e.text == good for e in detect_contextual("CF " + good))
    assert not any(e.pii_type == "FISCAL_CODE" for e in detect_contextual("CF RSS MRA 80A01 H501A"))


def test_birth_place_cues():
    for text in ("Luogo di nascita: Pavia (PV) il 12/03/1980", "nata in Pavia il 12/03/1980"):
        entities = detect_contextual(text)
        assert any(e.pii_type == "CITY_BORN" and e.text == "Pavia" for e in entities)
        assert any(e.pii_type == "DATE_BORN" and e.text == "12/03/1980" for e in entities)


def test_csv_columns_quotes_and_offsets():
    text = 'nome;email;note\r\n"Rossi, Mario";mario@example.it;ok\r\n"Anna ""Nina"" Bianchi";anna%40example.it;ok\r\n'
    entities = detect_tabular(text)
    assert [(e.pii_type, e.text) for e in entities] == [
        ("PERSON", "Rossi, Mario"), ("EMAIL", "mario@example.it"),
        ("PERSON", 'Anna ""Nina"" Bianchi'), ("EMAIL", "anna%40example.it"),
    ]
    assert all(text[e.start:e.end] == e.text for e in entities)


def test_csv_multiline_and_malformed_rows():
    text = 'nome,email,note\nMario,mario@example.it,"prima\nseconda"\nAnna,anna@example.it,ok\n'
    assert len(detect_tabular(text)) == 4
    assert not detect_tabular('nome,email\n"Mario,mario@example.it')
    assert not detect_tabular('prodotto,stato\nMario,ok\n')


def test_public_citation_does_not_suppress_private_case_identifier():
    text = "Cass. civile n. 12345/2020; pratica privata 12345/2020"
    first = text.index("12345")
    last = text.rindex("12345")
    spans = [entity(text, first, first + 10, "PRACTICE_ID"), entity(text, last, last + 10, "PRACTICE_ID")]
    assert precision_filter(spans, text=text) == [spans[1]]


def test_historical_date_requires_context_and_birth_dates_stay_protected():
    text = "Trattato del 16 giu 1979"
    start = text.index("16")
    date = entity(text, start, len(text), "DATE")
    birth = entity(text, start, len(text), "DATE_BORN")
    assert precision_filter([date, birth], text=text) == [birth]
    assert precision_filter([date]) == [date]


def test_placeholder_is_not_a_blanket_name_exclusion():
    text = "Tizio Caio Sempronio"
    assert not precision_filter([entity(text, 0, len(text), "PERSON")])
    assert precision_filter([entity("Tizio Rossi", 0, 11, "PERSON")])


def test_preposition_is_not_an_ml_phone_number():
    candidate = replace(entity("al", 0, 2, "PHONE"), source="rizzo")
    assert precision_filter([candidate]) == []


def test_street_named_after_person_keeps_address_type():
    text = "residente in Via Giuseppe Verdi 15"
    candidates = detect_contextual(text)
    start = text.index("Giuseppe")
    candidates.append(replace(entity(text, start, start + len("Giuseppe Verdi"), "PERSON"), source="rizzo"))
    merged = EntityMerger().merge(candidates, text)
    assert any(e.pii_type == "ADDRESS" and "Giuseppe Verdi" in e.text for e in merged)
    assert not any(e.pii_type == "PERSON" for e in merged)
