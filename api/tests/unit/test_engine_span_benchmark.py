import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[3] / 'benchmark/evaluate.py'
spec = importlib.util.spec_from_file_location('engine_evaluate', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_repeated_type_missing_one_occurrence_reduces_recall():
    spans = [dict(type='PERSON', start=0, end=3), dict(type='PERSON', start=4, end=7)]
    rows = [dict(id='repeated', text='Ada Ada', language='it', entities=spans)]
    result = module.evaluate(rows, lambda *args: (200, {'entities': spans[:1]}))
    assert result['recall'] == 0.5
    assert result['fn'] == 1


def test_duplicate_prediction_is_false_positive():
    span = dict(type='PERSON', start=0, end=3)
    rows = [dict(id='duplicate', text='Ada', language='it', entities=[span])]
    result = module.evaluate(rows, lambda *args: (200, {'entities': [span, span]}))
    assert result['precision'] == 0.5
    assert result['recall'] == 1.0


def test_wrong_offsets_do_not_count_as_correct():
    rows = [dict(id='offset', text='Ada ', language='it', entities=[dict(type='PERSON', start=0, end=3)])]
    result = module.evaluate(rows, lambda *args: (200, {'entities': [dict(type='PERSON', start=0, end=4)]}))
    assert result['tp'] == 0
    assert result['fp'] == result['fn'] == 1


def test_http_failure_never_becomes_a_quality_success():
    rows = [dict(id='error', text='Ada', language='it', entities=[])]
    with pytest.raises(RuntimeError, match='HTTP 503'):
        module.evaluate(rows, lambda *args: (503, {}))


def test_empty_corpus_rejected():
    with pytest.raises(ValueError, match='empty'):
        module.evaluate([], None)
