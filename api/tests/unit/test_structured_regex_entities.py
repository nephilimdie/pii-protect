from app.detection.layers.regex_layer import ItalianRegexDetector


def _entities(text: str):
    return ItalianRegexDetector([]).detect(text)


def test_detects_abbreviated_name_only_with_person_context():
    entities = _entities("Il referente M. Rossi ha confermato l'invio.")

    assert [(entity.pii_type, entity.text) for entity in entities] == [
        ("PERSON", "M. Rossi"),
    ]


def test_detects_compound_name_with_context():
    entities = _entities("Il contratto e intestato a Maria De Luca.")

    assert ("PERSON", "Maria De Luca") in {
        (entity.pii_type, entity.text) for entity in entities
    }


def test_does_not_treat_unrelated_capitalized_words_as_person():
    entities = _entities("Il Contratto Standard resta valido.")

    assert not any(entity.pii_type == "PERSON" for entity in entities)


def test_detects_structured_address_with_house_number_and_postcode():
    entities = _entities("Inviare la comunicazione a Via Roma 24, 20121 Milano.")

    assert [(entity.pii_type, entity.text) for entity in entities] == [
        ("ADDRESS", "Via Roma 24, 20121 Milano"),
    ]


def test_rejects_street_name_without_house_number():
    entities = _entities("La nota cita Via Roma senza numero civico.")

    assert not any(entity.pii_type == "ADDRESS" for entity in entities)
