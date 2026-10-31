"""Unit tests for the Italian PII benchmark harness (no Docker, no models).

Why: a benchmark whose generator or scorer is wrong produces confident wrong numbers.
What: checksum generators, gold-span integrity, determinism vs the committed dataset,
and the scorer's strict/lenient/leak/negative accounting on hand-built cases.
Test: python3 -m pytest benchmark/italian/tests -q
"""
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE / "systems")]

import generate  # noqa: E402
import itdata as D  # noqa: E402
import score  # noqa: E402
from common import load_docs, run_system  # noqa: E402

DATASET = HERE / "dataset" / "it_pii_v1.jsonl"


def test_should_build_known_codice_fiscale_and_omocodia():
    assert D.codice_fiscale("Mario", "Rossi", "M", 1980, 1, 1, "H501") == "RSSMRA80A01H501U"
    omo = D.codice_fiscale("Mario", "Rossi", "M", 1980, 1, 1, "H501", omocodia=1)
    assert omo[:14] == "RSSMRA80A01H50" and omo[14] == "M" and omo[15] == D.cf_check_char(omo[:15])


def test_should_generate_checksum_valid_identifiers_for_any_seed():
    for seed in range(50):
        rng = random.Random(seed)
        assert D.iban_valid(D.iban_it(rng))
        assert D.piva_valid(D.partita_iva(rng))
        assert D.luhn_valid(D.card_number(rng))
    assert D.iban_valid("IT60X0542811101000000123456") and not D.iban_valid("IT61X0542811101000000123456")


def test_should_match_committed_dataset_byte_for_byte():
    docs = generate.generate()
    payload = "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)
    assert payload == DATASET.read_text(encoding="utf-8")
    stats = json.loads(DATASET.with_suffix(".stats.json").read_text())
    assert stats["sha256"] == hashlib.sha256(payload.encode()).hexdigest()
    assert len(docs) >= 600 and stats["documents_without_pii"] >= 50


def test_should_have_valid_non_overlapping_gold_spans():
    for d in load_docs(DATASET):
        spans = sorted(d["entities"] + d["negatives"] + d["ignore"], key=lambda s: s["start"])
        for a, b in zip(spans, spans[1:]):
            assert a["end"] <= b["start"], (d["id"], a, b)
        for s in spans:
            assert 0 <= s["start"] < s["end"] <= len(d["text"])
        assert {e["type"] for e in d["entities"]} <= set(generate.PII_TYPES)


def _doc(text, entities, negatives=(), ignore=()):
    mk = lambda t, v: {"type": t, "start": text.index(v), "end": text.index(v) + len(v)}  # noqa: E731
    return {"id": "x", "genre": "g", "subgenre": "s", "text": text, "entities": [mk(t, v) for t, v in entities],
            "negatives": [mk(t, v) for t, v in negatives], "ignore": [mk(t, v) for t, v in ignore]}


TEXT = "Mario Rossi, CF RSSMRA80A01H501U, via Roma 12 Milano, art. 2043 c.c., P.IVA 01234567890."
DOC = _doc(TEXT, [("PERSON", "Mario Rossi"), ("FISCAL_CODE", "RSSMRA80A01H501U"), ("ADDRESS", "via Roma 12 Milano")],
           [("LAW_REF", "art. 2043 c.c.")], [("company_vat", "01234567890")])


def _span(t, v):
    return (t, TEXT.index(v), TEXT.index(v) + len(v))


def test_perfect_prediction_scores_one_and_leaks_nothing():
    preds = [_span("PERSON", "Mario Rossi"), _span("FISCAL_CODE", "RSSMRA80A01H501U"), _span("ADDRESS", "via Roma 12 Milano")]
    h = score.headline([score.score_doc(DOC, preds)])
    assert h["strict_f1"] == h["lenient_f1"] == 1.0 and h["leak_rate"] == 0.0 and h["neg_fp_rate"] == 0.0


def test_partial_address_is_lenient_hit_strict_miss_and_leaks_tokens():
    c = score.score_doc(DOC, [_span("ADDRESS", "via Roma 12")])
    assert c["strict_tp_type"]["ADDRESS"] == 0 and c["len_tp_type"]["ADDRESS"] == 1
    assert c["leak_type"]["ADDRESS"] == 1  # "Milano" stays in clear; "via", "Roma", "12" covered
    assert c["leak_type"]["PERSON"] == 2  # both name tokens unmasked


def test_wrong_type_counts_against_precision_but_not_leak():
    c = score.score_doc(DOC, [_span("PHONE", "RSSMRA80A01H501U")])
    h = score.headline([c])
    assert c["len_tp_type"]["FISCAL_CODE"] == 0 and h["lenient_p"] == 0.0
    assert c["leak_type"]["FISCAL_CODE"] == 0


def test_generic_classes_and_ignore_regions():
    assert score.compatible("GENERIC_ID", "FISCAL_CODE") and score.compatible("DATE", "DATE_OF_BIRTH")
    assert not score.compatible("PERSON", "ADDRESS") and score.compatible("ORG", "INDIRECT")
    c = score.score_doc(DOC, [_span("VAT_NUMBER", "01234567890"), _span("LAW_REF", "art. 2043 c.c.")])
    assert c["n_pred"] == 1 and c["neg_hit_type"]["LAW_REF"] == 1  # company VAT ignored, law ref is a FP


def test_direct_view_moves_quasi_identifiers_to_ignore():
    doc = _doc("R.G. 123/2024 Mario Rossi", [("CASE_ID", "123/2024"), ("PERSON", "Mario Rossi")])
    v = score.direct_view(doc)
    assert [e["type"] for e in v["entities"]] == ["PERSON"] and len(v["ignore"]) == 1


def test_bootstrap_identical_systems_have_zero_delta(tmp_path):
    counts = [score.score_doc(DOC, [_span("PERSON", "Mario Rossi")])] * 5
    ci = score.bootstrap({"a": counts, "b": counts}, "a", n=50)
    assert ci["b"]["delta_vs_reference"]["lenient_f1"] == [0.0, 0.0]


def test_run_system_writes_offsets_only(tmp_path):
    docs = load_docs(DATASET, 1)[:3]
    out = tmp_path / "fake.json"
    run_system(docs, lambda text: [("PERSON", 0, 1)], out, "fake", "pseudora", {"label": "fake"})
    data = json.loads(out.read_text())
    assert set(data["docs"]) == {d["id"] for d in docs}
    assert all(r["spans"] == [["PERSON", 0, 1]] for r in data["docs"].values())
    assert docs[0]["text"][:20] not in out.read_text()
