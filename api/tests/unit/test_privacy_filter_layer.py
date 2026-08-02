from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector


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
