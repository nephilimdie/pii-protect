"""Unit tests for the frozen TEST corpus it_pii_heldout_v2 (no Docker, no models).

Why: sprint-2 headline numbers are only meaningful if the corpus is exactly the frozen one, its
gold spans are well-formed and its pools stay disjoint from the development corpora.
What: checksums vs public examples, byte-for-byte rebuild vs the frozen sha256, span integrity,
PII-free near-miss documents, no name/town shared with it_pii_v1 or it_pii_heldout_v1 pools.
Test: python3 -m pytest benchmark/italian_heldout_v2/tests -q
"""
import hashlib
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import ident as I  # noqa: E402
from builder import PII_TYPES  # noqa: E402

_build_spec = importlib.util.spec_from_file_location("heldout_v2_build", HERE / "build.py")
build = importlib.util.module_from_spec(_build_spec)
_build_spec.loader.exec_module(build)

FROZEN = re.search(r"sha256: `([0-9a-f]{64})`", (HERE / "FREEZE.md").read_text()).group(1)


def test_should_match_public_checksum_examples():
    assert I.cf("Mario", "Rossi", False, 1980, 1, 1, "H501") == "RSSMRA80A01H501U"
    assert I.luhn("7992739871") == "3"
    assert I.mod97("IT", "X0542811101000000123456") == "60"


def test_should_generate_valid_codes_for_any_seed():
    for seed in range(50):
        r = random.Random(seed)
        p = I.person(r)
        assert p.cf[15] == I.check_letter(p.cf[:15])
        code = I.iban(r, r.choice(["IT", "PL", "BE", "PT", "AT"]))
        assert code[2:4] == I.mod97(code[:2], code[4:])
        v = I.piva(r)
        assert v[10] == I.luhn(v[:10])
        c = I.card(r)
        assert c[-1] == I.luhn(c[:-1])


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
        if d["genre"] == "negative":
            assert not d["entities"], d["id"]


def test_should_not_share_name_or_town_pools_with_dev_corpora():
    pools = set(I.M + I.F + I.SUR + I.PARTICLE_SUR + [n for v in I.FOREIGN.values() for n in v[0] + v[1] + v[2]])
    pools |= {t[0] for t in I.TOWNS}
    for f in (HERE.parent / "italian_heldout" / "fakedata.py", HERE.parent / "italian" / "itdata.py"):
        words = set(re.findall(r"[A-ZÀ-Ý][\w'àèéìòù]+(?: [A-Z][\w']+)?", f.read_text(encoding="utf-8")))
        assert not pools & words, (f.name, sorted(pools & words))
