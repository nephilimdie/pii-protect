from types import SimpleNamespace

from app.detection.entities import PiiEntity
from app.documents.identity_fields import supplement_identity_fields
from app.documents.models import JoinedText


CARD = """PATENTE DI GUIDA
1.
BRAMBILLA
2.
GIANFRANCO
3.
14/03/1979 L0DI (LO)
4a.
02/09/2021
5.
U1R7K4Q9Z2
6.
BRMGFR79C14E648T"""

US_CARD = """DRIVER'SLICENSE
Pennsylvania
USA
99 999 999
DUPS:00
4dDLN:
01/07/1973
DOB:
SAMPLE
ANDREW JASON
123MAINSTREET
APT.1
HARRISBURG,PA17101-0000
5DD:1234567890123
ORGAN DONOR"""


def _doc(text):
    return SimpleNamespace(scanned={0: SimpleNamespace(text=text)})


def test_numbered_driving_licence_fields_fill_detection_gaps():
    joined = JoinedText([CARD])
    name_start = CARD.index("GIANFRANCO")
    detected = [PiiEntity(name_start, name_start + 10, "PERSON", "GIANFRANCO", 0.9)]
    result = supplement_identity_fields(_doc(CARD), joined, detected)
    values = {(item.pii_type, item.text) for item in result}
    assert ("PERSON", "BRAMBILLA") in values
    assert ("DATE_OF_BIRTH", "14/03/1979") in values
    assert ("LOCATION", "L0DI (LO)") in values
    assert ("DRIVER_LICENSE", "U1R7K4Q9Z2") in values
    assert ("FISCAL_CODE", "BRMGFR79C14E648T") in values
    assert len([item for item in result if item.text == "GIANFRANCO"]) == 1
    assert all(joined.text[item.start:item.end] == item.text for item in result)


def test_generic_document_and_incomplete_card_do_not_gain_entities():
    generic = CARD.replace("PATENTE DI GUIDA", "RIEPILOGO")
    partial = "PATENTE DI GUIDA\n1. BRAMBILLA\n2. GIANFRANCO"
    for text in (generic, partial):
        assert supplement_identity_fields(_doc(text), JoinedText([text]), []) == []


def test_inline_field_numbers_and_second_page_offsets():
    card = "PATENTE DI GUIDA\n1: BRAMBILLA\n2: GIANFRANCO\n3: 14/03/1979 LODI\n5: U1R7K4Q9Z2"
    joined = JoinedText(["cover page", card])
    doc = SimpleNamespace(scanned={1: SimpleNamespace(text=card)})
    result = supplement_identity_fields(doc, joined, [])
    assert {item.pii_type for item in result} == {"PERSON", "DATE_OF_BIRTH", "LOCATION", "DRIVER_LICENSE"}
    assert all(joined.text[item.start:item.end] == item.text for item in result)


def test_numbered_context_refines_generic_date_and_account_labels():
    joined = JoinedText([CARD])
    detected = []
    for value, pii_type in (("14/03/1979", "DATE"), ("U1R7K4Q9Z2", "ACCOUNT_NUMBER")):
        start = CARD.index(value)
        detected.append(PiiEntity(start, start + len(value), pii_type, value, 0.9))
    result = supplement_identity_fields(_doc(CARD), joined, detected)
    assert len(result) == len({(item.start, item.end) for item in result})
    assert {item.pii_type for item in result} >= {"DATE_OF_BIRTH", "DRIVER_LICENSE"}
    assert all(item.source == "document_layout" for item in result if item.pii_type in {"DATE_OF_BIRTH", "DRIVER_LICENSE"})


def test_us_driving_licence_fields_cover_ocr_values_missed_by_ner():
    joined = JoinedText([US_CARD])
    existing = PiiEntity(US_CARD.index("ANDREW JASON"), US_CARD.index("ANDREW JASON") + 12,
                         "PERSON", "ANDREW JASON", 0.9)
    result = supplement_identity_fields(_doc(US_CARD), joined, [existing])
    values = {(item.pii_type, item.text) for item in result}
    assert {("DRIVER_LICENSE", "99 999 999"), ("PERSON", "SAMPLE"),
            ("LOCATION", "123MAINSTREET"), ("LOCATION", "APT.1"),
            ("LOCATION", "HARRISBURG,PA17101-0000"),
            ("DRIVER_LICENSE", "1234567890123")} <= values
    assert len([item for item in result if item.text == "ANDREW JASON"]) == 1
    assert all(joined.text[item.start:item.end] == item.text for item in result)


def test_us_fields_do_not_apply_without_licence_title():
    text = US_CARD.replace("DRIVER'SLICENSE", "CUSTOMER RECORD")
    assert supplement_identity_fields(_doc(text), JoinedText([text]), []) == []
