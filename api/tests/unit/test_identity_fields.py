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
