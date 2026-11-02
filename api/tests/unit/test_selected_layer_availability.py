from types import SimpleNamespace

import pytest

from app.anonymization.anonymizer import PiiAnonymizer
from app.detection.detector_registry import DetectorRegistry


def registry():
    result = DetectorRegistry()
    result.register(SimpleNamespace(layer_name="rizzo", priority=50, is_available=lambda: False))
    return result


def test_selected_unavailable_layer_blocks_detection():
    with pytest.raises(RuntimeError, match="unavailable"):
        PiiAnonymizer(registry())._run_detectors("Mario Rossi", "it")


def test_disabled_unavailable_layer_does_not_block_detection():
    assert PiiAnonymizer(registry(), enabled_layers=set())._run_detectors("Mario Rossi", "it") == []


def test_unregistered_selected_layer_blocks_detection():
    with pytest.raises(RuntimeError, match="not installed"):
        PiiAnonymizer(DetectorRegistry(), enabled_layers={"rizzo"})._run_detectors("Mario Rossi", "it")


def test_level_exclusion_does_not_block_but_explicit_selection_does():
    detector = PiiAnonymizer(registry(), layer_levels={"rizzo": frozenset({"maximum"})})
    assert detector._run_detectors("Mario Rossi", "it") == []
    detector.restrict_layers(["rizzo"])
    with pytest.raises(RuntimeError, match="unavailable"):
        detector._run_detectors("Mario Rossi", "it")
