from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector, _materialize_onnx_files


def fake_tokenizer():
    def encode(line: str, add_special_tokens: bool = False):
        del add_special_tokens
        words = line.split()
        offsets = []
        cursor = 0
        for word in words:
            start = line.index(word, cursor)
            offsets.append((start, start + len(word)))
            cursor = start + len(word)
        return SimpleNamespace(ids=list(range(1, len(words) + 1)), offsets=offsets)

    def token_to_id(token: str) -> int:
        return 0 if token == "[PAD]" else 1

    return SimpleNamespace(encode=encode, token_to_id=token_to_id)


def fake_session(fail_batches: bool = False):
    batch_sizes: list[int] = []

    def get_inputs():
        return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

    def run(_outputs, inputs):
        batch_size, sequence_length = inputs["input_ids"].shape
        batch_sizes.append(batch_size)
        if fail_batches and batch_size > 1:
            raise RuntimeError("dynamic batches unavailable")

        logits = np.zeros((batch_size, sequence_length, 33), dtype=np.float32)
        logits[:, :, 20] = 10.0  # S-private_person
        return [logits]

    return SimpleNamespace(
        batch_sizes=batch_sizes,
        get_inputs=get_inputs,
        run=run,
    )


def detector(session) -> PrivacyFilterDetector:
    subject = PrivacyFilterDetector()
    subject._tokenizer = fake_tokenizer()
    subject._session = session
    return subject


def test_multiline_detection_uses_one_onnx_batch_and_preserves_offsets():
    session = fake_session()
    entities = detector(session)._run("Mario Rossi\nAnna", min_score=0.7)

    assert session.batch_sizes == [2]
    assert [entity.text for entity in entities] == ["Mario", "Rossi", "Anna"]
    assert [(entity.start, entity.end) for entity in entities] == [(0, 5), (6, 11), (12, 16)]


def test_batch_failure_falls_back_to_single_line_inference():
    session = fake_session(fail_batches=True)
    entities = detector(session)._run("Mario\nAnna", min_score=0.7)

    assert session.batch_sizes == [2, 1, 1]
    assert [entity.text for entity in entities] == ["Mario", "Anna"]


def test_long_line_covers_all_tokens_without_duplicate_spans():
    subject = detector(fake_session())
    text = " ".join(f"word{index}" for index in range(1100))
    entities = subject._run(text)
    assert len(entities) == 1100
    assert entities[-1].text == "word1099"
    assert entities[-1].end == len(text)
    assert all(text[item.start:item.end] == item.text for item in entities)


def test_single_line_entrypoint_preserves_global_offsets_across_windows():
    subject = detector(fake_session())
    text = " ".join(["Mario"] * 600)
    entities = subject._run_line(text, 20)
    assert len(entities) == 600
    assert entities[0].start == 20
    assert entities[-1].end == 20 + len(text)


def test_privacy_filter_inference_failure_is_not_reported_as_no_pii():
    subject = detector(fake_session())
    def fail(*args):
        raise RuntimeError("inference unavailable")
    subject._session.run = fail
    with pytest.raises(RuntimeError, match="inference unavailable"):
        subject.detect("Mario Rossi")


def test_materialize_onnx_external_data_uses_real_files(tmp_path):
    source_dir = tmp_path / "onnx"
    source_dir.mkdir()
    model_source = tmp_path / "model.onnx"
    data_source = tmp_path / "model.onnx_data"
    model_source.write_bytes(b"model")
    data_source.write_bytes(b"external-data")
    (source_dir / "model_quantized.onnx").symlink_to(model_source)
    (source_dir / "model_quantized.onnx_data").symlink_to(data_source)

    model_path = _materialize_onnx_files(str(tmp_path))

    assert model_path.endswith(".materialized-onnx/model_quantized.onnx")
    assert os.path.isfile(model_path)
    assert not os.path.islink(model_path)
    with open(model_path, "rb") as model_file:
        assert model_file.read() == b"model"
    data_path = os.path.join(os.path.dirname(model_path), "model_quantized.onnx_data")
    with open(data_path, "rb") as data_file:
        assert data_file.read() == b"external-data"
