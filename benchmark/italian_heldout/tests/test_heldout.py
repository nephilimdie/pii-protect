"""Unit tests for the held-out corpus it_pii_heldout_v1 (no Docker, no models).

Why: the held-out numbers are only meaningful if the corpus is exactly the frozen one and its
gold spans are well-formed.
What: checksum helpers vs public examples, byte-for-byte rebuild vs the committed file and its
frozen sha256, span integrity, and PII-free negative documents.
Test: python3 -m pytest benchmark/italian_heldout/tests -q
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build  # noqa: E402
import fakedata as F  # noqa: E402
from markup import NEG_TYPES, PII_TYPES  # noqa: E402

FROZEN = re.search(r"sha256: `([0-9a-f]{64})`", (HERE / "FREEZE.md").read_text()).group(1)


def test_should_match_public_checksum_examples():
    assert F.codice_fiscale("Mario", "Rossi", False, 1980, 1, 1, "H501") == "RSSMRA80A01H501U"
    assert F.luhn_digit("7992739871") == "3"
    assert F.iban_check("IT", "X0542811101000000123456") == "60"


def test_should_generate_valid_cf_iban_and_piva_for_any_seed():
    import random
    for seed in range(40):
        rng = random.Random(seed)
        p = F.persona(rng)
        assert p.cf[15] == F.control_char(p.cf[:15])
        iban = F.iban(rng, rng.choice(["IT", "DE", "FR", "ES", "RO"]))
        assert iban[2:4] == F.iban_check(iban[:2], iban[4:])
        v = F.partita_iva(rng)
        assert v[10] == F.luhn_digit(v[:10])


def test_should_rebuild_frozen_corpus_byte_for_byte():
    text = build.payload(build.generate())
    assert text == build.DATASET.read_text(encoding="utf-8")
    assert hashlib.sha256(text.encode()).hexdigest() == FROZEN
    assert json.loads(build.DATASET.with_suffix(".stats.json").read_text())["sha256"] == FROZEN


def test_should_have_valid_spans_and_pii_free_negatives():
    docs = [json.loads(line) for line in build.DATASET.read_text(encoding="utf-8").splitlines()]
    assert len([d for d in docs if d["entities"]]) >= 300 and len([d for d in docs if d["genre"] == "negative"]) >= 90
    for d in docs:
        spans = sorted(d["entities"] + d["negatives"] + d["ignore"], key=lambda s: s["start"])
        for a, b in zip(spans, spans[1:]):
            assert a["end"] <= b["start"], (d["id"], a, b)
        for s in spans:
            v = d["text"][s["start"]:s["end"]]
            assert v and v == v.strip(), (d["id"], s)
        assert {e["type"] for e in d["entities"]} <= set(PII_TYPES)
        assert {n["type"] for n in d["negatives"]} <= set(NEG_TYPES)
        if d["genre"] == "negative":
            assert not d["entities"], d["id"]
