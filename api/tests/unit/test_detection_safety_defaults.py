from unittest.mock import Mock

import pytest

from app.anonymization.anonymizer import _snap_to_word_boundary
from app.detection.entities import PiiEntity
from app.detection.layer_config import effective
from app.detection.layers.presidio_layer import PresidioDetector


@pytest.mark.parametrize('layer', ['privacy_filter', 'ai4privacy'])
def test_short_text_detection_enabled_by_default_but_explicit_override_respected(layer):
    assert effective(layer, None, None)['min_chars'] == 0
    assert effective(layer, {'min_chars': 200}, None)['min_chars'] == 200


@pytest.mark.parametrize('prefix', ['é', 'e\u0301', 'ü'])
def test_unicode_email_prefix_is_not_left_in_original_text(prefix):
    address = prefix + 'lise@example.org'
    text = 'Email: ' + address
    start = text.index('lise')
    entity = PiiEntity(start=start, end=len(text), text=text[start:], pii_type='EMAIL', score=1)
    result = _snap_to_word_boundary(text, entity)
    assert result.text == address
    assert result.start == len('Email: ')


def test_presidio_failure_is_not_silently_treated_as_no_entities():
    detector = PresidioDetector()
    detector._analyzer = Mock()
    detector._analyzer.analyze.side_effect = RuntimeError('model failed')
    with pytest.raises(RuntimeError, match='model failed'):
        detector.detect('Ada Lovelace')


@pytest.mark.parametrize('title', [
    'sig.', 'sig.ra', 'sigg.', 'dott.', 'dott.ssa', 'avv.', 'ing.', 'geom.', 'rag.',
    'prof.', 'prof.ssa', 'arch.', 'notaio', 'Sig.ra', 'Dott.', 'AVV.', 'la sig.ra', 'il dott.',
])
def test_person_span_drops_leading_title_but_keeps_full_name(title):
    text = f'Presente {title} Giulia Verdi, residente a Milano.'
    start = text.index(title)
    entity = PiiEntity(start=start, end=text.index(','), text='', pii_type='PERSON', score=1)
    result = _snap_to_word_boundary(text, entity)
    assert result.text == 'Giulia Verdi'
    assert result.start == text.index('Giulia')


@pytest.mark.parametrize('name', ['Giulia Verdi', 'La Russa Ignazio', 'Arch Stanton', 'Ing Rossi'])
def test_person_span_without_title_is_unchanged_and_not_expanded_over_preceding_title(name):
    text = f'La sig.ra {name}, ok'
    start = text.index(name)
    entity = PiiEntity(start=start, end=start + len(name), text=name, pii_type='PERSON', score=1)
    assert _snap_to_word_boundary(text, entity).text == name


@pytest.mark.parametrize('address', ['n.rossi@x.it', 'pec.rossi@x.it', 'cf.rossi@x.it', 'nato.rossi@x.it', 'n.-rossi@x.it',
                                     'tel.rossi@x.it'])
@pytest.mark.parametrize('pii_type', ['EMAIL', 'PERSON'])
def test_label_like_email_local_part_is_never_stripped(address, pii_type):
    text = f'Scrivere a {address} oppure email: {address}'
    for start in (text.index(address), text.index('email:')):
        end = text.index(address, start) + len(address)
        entity = PiiEntity(start=start, end=end, text=text[start:end], pii_type=pii_type, score=1)
        result = _snap_to_word_boundary(text, entity)
        assert text[result.start:result.end] == address


@pytest.mark.parametrize('pii_type,value', [('URL', 'pec.example.it/x'), ('IBAN', 'IT60X0542811101000000123456')])
def test_label_glued_to_url_or_iban_is_not_cut(pii_type, value):
    text = f'link n.{value}'
    entity = PiiEntity(start=5, end=len(text), text=text[5:], pii_type=pii_type, score=1)
    assert _snap_to_word_boundary(text, entity).text == f'n.{value}'


@pytest.mark.parametrize('span', ['Dati: nome Mario Rossi', 'nome Mario Rossi', 'Dati anagrafici: cognome e nome Mario Rossi',
                                  'Nominativo: Sig.ra Mario Rossi', 'Dati: nome Sig. Mario Rossi'])
def test_person_span_drops_leading_label_words(span):
    text = f'{span}, nato a Roma.'
    entity = PiiEntity(start=0, end=len(span), text=span, pii_type='PERSON', score=1)
    result = _snap_to_word_boundary(text, entity)
    assert (result.text, result.start) == ('Mario Rossi', text.index('Mario'))


def test_person_span_that_is_only_label_words_is_dropped():
    text = 'Dati: nome Mario'
    assert _snap_to_word_boundary(text, PiiEntity(start=0, end=10, text='Dati: nome', pii_type='PERSON', score=1)) is None


@pytest.mark.parametrize('name', ['Perla Rossi', 'Nomellini Carlo', 'Dationi Luca'])
def test_names_starting_like_label_words_are_kept(name):
    text = f'{name}, ok'
    entity = PiiEntity(start=0, end=len(name), text=name, pii_type='PERSON', score=1)
    assert _snap_to_word_boundary(text, entity).text == name
