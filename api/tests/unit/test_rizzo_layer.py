"""Unit tests for the Rizzo-PII layer without the model (fake HF pipeline).

Why: chunk offsets, tag mapping, span widening and address fusion decide what gets masked.
What: drives RizzoDetector.detect with a pipeline stub returning aggregated entities per chunk.
Test: pytest tests/unit/test_rizzo_layer.py
"""
import pytest

from app.anonymization.anonymizer import PiiAnonymizer
from app.detection.detector_registry import DetectorRegistry
from app.detection.layers import rizzo_layer as R


class _Pipe:
    def __init__(self, finder):
        self.finder = finder

    def __call__(self, texts):
        return [self.finder(t) for t in texts]


def _ent(text, value, group, score=0.99, cut=0):
    i = text.find(value)
    return [] if i < 0 else [{"entity_group": group, "start": i + cut, "end": i + len(value), "score": score}]


def _detect(text, finder, cfg=None):
    R.RizzoDetector._pipeline = _Pipe(finder)
    try:
        return R.RizzoDetector().detect(text, "it", cfg)
    finally:
        R.RizzoDetector._pipeline = None


def test_should_chunk_whole_words_with_overlap():
    assert R.chunks("a b c", 2, 1) == [("a b", 0), ("b c", 2)]
    text = " ".join(f"w{i}" for i in range(300))
    parts = R.chunks(text)
    assert len(parts) == 3 and all(text[o:o + len(c)] == c for c, o in parts)


def test_should_map_tags_and_drop_non_pii_tags():
    text = "MARIO ROSSI paga 100 euro alla Edil S.r.l."
    out = _detect(text, lambda t: _ent(t, "MARIO ROSSI", "FULLNAME") + _ent(t, "100 euro", "AMOUNT") + _ent(t, "Edil S.r.l.", "ORG"))
    assert [(e.pii_type, e.text, e.source) for e in out] == [("PERSON", "MARIO ROSSI", "rizzo")]


def test_should_widen_partial_word_and_respect_threshold():
    text = "nato a Novara il 3/2/1980"
    out = _detect(text, lambda t: _ent(t, "Novara", "CITY", cut=2) + _ent(t, "3/2/1980", "DATE", score=0.3))
    assert [(e.pii_type, e.text) for e in out] == [("ADDRESS", "Novara")]


def test_should_fuse_address_parts_and_drop_lone_house_number():
    text = "residente in Via Roma 12, 00185 Roma. Civico 7"
    finder = lambda t: (_ent(t, "Via Roma", "STREET") + _ent(t, "12", "BUILDINGNUM") + _ent(t, "00185", "ZIPCODE")  # noqa: E731
                        + [{"entity_group": "CITY", "start": t.rfind("Roma"), "end": t.rfind("Roma") + 4, "score": .9}]
                        + _ent(t, "7", "BUILDINGNUM"))
    out = _detect(text, finder)
    assert [(e.pii_type, e.text) for e in out] == [("ADDRESS", "Via Roma 12, 00185 Roma")]


def test_should_offset_entities_from_later_chunks():
    text = " ".join(["parola"] * 150) + " Ezio Gargiulo"
    out = _detect(text, lambda t: _ent(t, "Ezio Gargiulo", "FULLNAME"))
    assert len(out) == 1 and text[out[0].start:out[0].end] == "Ezio Gargiulo"


def test_should_fail_closed_without_model():
    with pytest.raises(RuntimeError, match="unavailable"):
        R.RizzoDetector().detect("Mario Rossi")


def test_should_fail_closed_on_inference_error(monkeypatch):
    def fail(_):
        raise ValueError("private input")
    monkeypatch.setattr(R.RizzoDetector, "_pipeline", staticmethod(fail))
    with pytest.raises(RuntimeError, match="inference failed") as exc:
        R.RizzoDetector().detect("Mario Rossi")
    assert "private input" not in str(exc.value)


@pytest.mark.parametrize("output", [[], None, [[{"entity_group": "FULLNAME", "start": 0, "end": 999, "score": 1}]]])
def test_should_reject_incomplete_or_invalid_results(monkeypatch, output):
    monkeypatch.setattr(R.RizzoDetector, "_pipeline", staticmethod(lambda _: output))
    with pytest.raises(RuntimeError):
        R.RizzoDetector().detect("Mario Rossi")


def test_should_clear_previous_model_if_revision_is_missing(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text("{}")
    monkeypatch.setattr(R.RizzoDetector, "_pipeline", object())
    R.RizzoDetector.preload(str(tmp_path), "expected-revision")
    assert not R.RizzoDetector().is_available()


def test_should_gate_layer_by_protection_level_unless_named():
    a = PiiAnonymizer(DetectorRegistry(), layer_levels={"rizzo": frozenset({"maximum"})})
    assert not a._runs_at_level("rizzo") and a._runs_at_level("presidio")
    a.set_protection_level("maximum")
    assert a._runs_at_level("rizzo")
    a.set_protection_level("balanced")
    a.restrict_layers(["regex", "rizzo"])
    assert a._runs_at_level("rizzo")
