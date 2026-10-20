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
