from unittest.mock import Mock

import pytest

from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector


def test_inference_failure_propagates_to_fail_closed_handler():
    detector = Ai4PrivacyDetector()
    detector._pipeline = Mock(side_effect=RuntimeError("inference unavailable"))
    with pytest.raises(RuntimeError, match="inference unavailable"):
        detector.detect("test " * 50)


def test_long_text_uses_overlapping_transformer_windows():
    detector = Ai4PrivacyDetector()
    detector._pipeline = Mock(return_value=[])
    text = "test " * 600
    assert detector.detect(text) == []
    detector._pipeline.assert_called_once_with(text, stride=64)


def test_short_text_is_analyzed_unless_explicitly_skipped():
    detector = Ai4PrivacyDetector()
    detector._pipeline = Mock(return_value=[])
    detector.detect('Ada')
    detector._pipeline.assert_called_once()
    detector._pipeline.reset_mock()
    detector.detect('Ada', layer_config={'min_chars': 200})
    detector._pipeline.assert_not_called()
