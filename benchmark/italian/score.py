"""Score system predictions against the it_pii_v1 gold annotations.

Why: one scorer, one taxonomy and one set of matching rules for every system, so the
comparison is apples to apples and re-computable from committed predictions.
What: per document counts -> strict (exact span + compatible type, one-to-one) and lenient
(overlap + compatible type) precision/recall/F1, token leak rate (gold word tokens not fully
covered by any masked span, type-agnostic), false-positive rate on negative look-alikes,
latency per 1k chars; per type / genre / hard case; document-level bootstrap 95% CIs and
paired deltas against a reference system.
Test: tests/test_italian_bench.py scores hand-built predictions with known expected counts.

Usage: python3 score.py --predictions results/predictions --out results [--reference pseudora_generic_professional]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "systems"))
from common import load_docs  # noqa: E402

TAX = json.loads((HERE / "taxonomy.json").read_text())
_WORD = re.compile(r"[^\W_]+")
# label words inside gold spans that identify nobody ("n. 4", "foglio 12", "int. 5"): not leaks
_LABEL_TOKENS = {"n", "nr", "int", "sub", "subalterno", "foglio", "fg", "f", "particella", "p", "lla", "mappale",
                 "mapp", "loc", "località", "fraz", "contrada", "c", "da"}
# quasi-identifiers whose "must mask" status depends on the use case; the "direct" view ignores them
INDIRECT_TYPES = {"BIRTH_PLACE", "CASE_ID", "CONTRACT_ID", "CADASTRAL_REF", "INDIRECT"}
BOOTSTRAP = 1000


def canon(family: str, label: str) -> str:
    return TAX["systems"][family].get(label, "OTHER")


def compatible(pred: str, gold: str) -> bool:
    """Why: systems use coarser or finer labels than the gold; only declared equivalences count.
    What: equal labels, a generic prediction class covering the gold type, or a type-free gold type.
    Test: compatible('DATE','DATE_OF_BIRTH') and not compatible('PHONE','IBAN').
    """
    return pred == gold or gold in TAX["compatible"].get(pred, ()) or gold in TAX["any_type"]


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def score_doc(doc: dict, preds: list[tuple[str, int, int]]) -> dict:
    """Why: every metric is a sum of per-document counts, which makes bootstrap resampling exact.
    What: preds = [(canonical_type, start, end)]; returns counts for all metrics of one document.
    Test: a perfect prediction gives strict tp == len(gold), fp == 0, leaked == 0.
    """
    gold = [(e["type"], e["start"], e["end"], tuple(e.get("hard", ()))) for e in doc["entities"]]
    ign = [(s["start"], s["end"]) for s in doc["ignore"]]
    # predictions touching only an "ignore" region (e.g. a company VAT) are neither right nor wrong
    preds = [p for p in preds if not any(_overlap(p[1:], i) for i in ign)
             or any(_overlap(p[1:], g[1:3]) for g in gold)]
    c: dict = {"n_gold": len(gold), "n_pred": len(preds), "chars": len(doc["text"]),
               "gold_type": Counter(), "strict_tp_type": Counter(), "len_tp_type": Counter(),
               "pred_type": Counter(), "pred_ok_type": Counter(), "hard": Counter(), "hard_hit": Counter(),
               "tok_type": Counter(), "leak_type": Counter(), "neg_type": Counter(), "neg_hit_type": Counter()}
    used: set[int] = set()
    for gt, gs, ge, hard in gold:
        c["gold_type"][gt] += 1
        hit = next((k for k, p in enumerate(preds) if k not in used and p[1] == gs and p[2] == ge and compatible(p[0], gt)), None)
        if hit is not None:
            used.add(hit)
            c["strict_tp_type"][gt] += 1
        lenient = any(_overlap(p[1:], (gs, ge)) and compatible(p[0], gt) for p in preds)
        c["len_tp_type"][gt] += lenient
        for h in hard:
            c["hard"][h] += 1
            c["hard_hit"][h] += lenient
    covered = [False] * len(doc["text"])
    for _, s, e in preds:
        covered[s:e] = [True] * (e - s)
    for gt, gs, ge, _ in gold:
        for m in _WORD.finditer(doc["text"], gs, ge):
            if m.group().casefold() in _LABEL_TOKENS:
                continue
            c["tok_type"][gt] += 1
            c["leak_type"][gt] += not all(covered[m.start():m.end()])
    for pt, s, e in preds:
        c["pred_type"][pt] += 1
        c["pred_ok_type"][pt] += any(_overlap((s, e), g[1:3]) and compatible(pt, g[0]) for g in gold)
    for n in doc["negatives"]:
        c["neg_type"][n["type"]] += 1
        c["neg_hit_type"][n["type"]] += any(_overlap((n["start"], n["end"]), p[1:]) for p in preds)
    c["sum"] = {k: sum(c[k].values()) for k in ("strict_tp_type", "len_tp_type", "pred_ok_type", "tok_type",
                                                 "leak_type", "neg_type", "neg_hit_type")}
    c["neg_doc"] = not gold
    c["neg_doc_flagged"] = not gold and bool(preds)
    return c


def direct_view(doc: dict) -> dict:
    """What: same document with quasi-identifier gold spans turned into ignore regions."""
    keep = [e for e in doc["entities"] if e["type"] not in INDIRECT_TYPES]
    moved = [{"type": e["type"], "start": e["start"], "end": e["end"]} for e in doc["entities"] if e["type"] in INDIRECT_TYPES]
    return {**doc, "entities": keep, "ignore": doc["ignore"] + moved}


def _prf(tp_r: float, n_gold: float, tp_p: float, n_pred: float) -> tuple[float, float, float]:
    r = tp_r / n_gold if n_gold else 1.0
    p = tp_p / n_pred if n_pred else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def headline(counts: list[dict]) -> dict:
    """What: overall metrics from a list of per-document counts (also used per bootstrap sample)."""
    s = lambda key: sum(c["sum"][key] for c in counts)  # noqa: E731
    ng, npred = sum(c["n_gold"] for c in counts), sum(c["n_pred"] for c in counts)
    stp, ltp, lok = s("strict_tp_type"), s("len_tp_type"), s("pred_ok_type")
    sp, sr, sf = _prf(stp, ng, stp, npred)
    lp, lr, lf = _prf(ltp, ng, lok, npred)
    toks, negs = s("tok_type"), s("neg_type")
    return {"strict_p": sp, "strict_r": sr, "strict_f1": sf, "lenient_p": lp, "lenient_r": lr, "lenient_f1": lf,
            "leak_rate": s("leak_type") / toks if toks else 0.0,
            "neg_fp_rate": s("neg_hit_type") / negs if negs else 0.0,
            "n_gold": ng, "n_pred": npred}


def breakdown(counts: list[dict]) -> dict:
    tot = defaultdict(Counter)
    for c in counts:
        for k, v in c.items():
            if isinstance(v, Counter):
                tot[k].update(v)
    per_type = {}
    for t, n in sorted(tot["gold_type"].items()):
        per_type[t] = {"gold": n, "strict_recall": tot["strict_tp_type"][t] / n, "lenient_recall": tot["len_tp_type"][t] / n,
                       "leak_rate": tot["leak_type"][t] / tot["tok_type"][t] if tot["tok_type"][t] else 0.0}
    pred_precision = {t: {"pred": n, "lenient_precision": tot["pred_ok_type"][t] / n} for t, n in sorted(tot["pred_type"].items())}
    neg = {t: {"spans": n, "masked_rate": tot["neg_hit_type"][t] / n} for t, n in sorted(tot["neg_type"].items())}
    hard = {h: {"spans": n, "lenient_recall": tot["hard_hit"][h] / n} for h, n in sorted(tot["hard"].items())}
    nd = sum(c["neg_doc"] for c in counts)
    return {"per_type": per_type, "pred_precision": pred_precision, "negatives": neg, "hard_cases": hard,
            "negative_docs": nd, "negative_docs_flagged_rate": sum(c["neg_doc_flagged"] for c in counts) / nd if nd else 0.0}


def _ci(values: list[float]) -> list[float]:
    v = sorted(values)
    return [round(v[int(.025 * len(v))], 4), round(v[min(len(v) - 1, int(.975 * len(v)))], 4)]


def bootstrap(per_system: dict[str, list[dict]], reference: str | None, n: int = BOOTSTRAP, seed: int = 7) -> dict:
    """Why: 750 documents is a sample; CIs show which gaps are noise.
    What: resamples documents (same indices for every system => paired deltas vs reference).
    Test: identical systems give a delta CI of [0, 0].
    """
    rng = random.Random(seed)
    k = len(next(iter(per_system.values())))
    keys = ("strict_f1", "lenient_f1", "lenient_r", "lenient_p", "leak_rate", "neg_fp_rate")
    samples = {s: {m: [] for m in keys} for s in per_system}
    deltas = {s: {m: [] for m in ("lenient_f1", "strict_f1", "leak_rate")} for s in per_system}
    for _ in range(n):
        idx = [rng.randrange(k) for _ in range(k)]
        hs = {s: headline([cs[i] for i in idx]) for s, cs in per_system.items()}
        for s, h in hs.items():
            for m in keys:
                samples[s][m].append(h[m])
            if reference in hs:
                for m in deltas[s]:
                    deltas[s][m].append(h[m] - hs[reference][m])
    out = {s: {m: _ci(v) for m, v in ms.items()} for s, ms in samples.items()}
    if reference in per_system:
        for s in per_system:
            out[s]["delta_vs_reference"] = {m: _ci(v) for m, v in deltas[s].items()}
    return out


def load_predictions(path: Path, docs: dict[str, dict]) -> tuple[dict, list[dict]]:
    pred = json.loads(path.read_text())
    missing = set(docs) - set(pred["docs"])
    if missing:
        raise ValueError(f"{path.name}: {len(missing)} documents without predictions")
    counts, direct, ms, chars = [], [], 0.0, 0
    for doc_id, doc in docs.items():
        row = pred["docs"][doc_id]
        spans = [(canon(pred["family"], lab), s, e) for lab, s, e in row["spans"]]
        counts.append(score_doc(doc, spans))
        direct.append(score_doc(direct_view(doc), spans))
        ms += row["ms"]
        chars += len(doc["text"])
    return {**pred["meta"], "system": pred["system"], "family": pred["family"],
            "ms_per_1k_chars": round(ms / chars * 1000, 2)}, counts, direct


def score_all(dataset: Path, pred_dir: Path, reference: str | None, n_boot: int = BOOTSTRAP, subset: int = 0) -> dict:
    """What: loads every predictions/*.json, returns the full results object (no text inside)."""
    docs = {d["id"]: d for d in load_docs(dataset, subset)}
    systems, per_system, per_system_direct = {}, {}, {}
    for path in sorted(pred_dir.glob("*.json")):
        meta, counts, direct = load_predictions(path, docs)
        per_system[meta["system"]] = counts
        per_system_direct[meta["system"]] = direct
        genres = defaultdict(list)
        for doc, c in zip(docs.values(), counts):
            genres[doc["genre"]].append(c)
        systems[meta["system"]] = {"meta": meta, "overall": headline(counts), "direct": headline(direct), **breakdown(counts),
                                   "per_genre": {g: headline(cs) for g, cs in sorted(genres.items())}}
    for s, ci in bootstrap(per_system, reference, n_boot).items():
        systems[s]["ci95"] = ci
    for s, ci in bootstrap(per_system_direct, reference, n_boot).items():
        systems[s]["ci95_direct"] = ci
    return {"dataset": dataset.name, "documents": len(docs), "subset_per_subgenre": subset, "bootstrap_samples": n_boot, "reference": reference,
            "matching": {"strict": "exact start/end + compatible type, one-to-one",
                         "lenient": "any overlap + compatible type (recall per gold span, precision per predicted span)",
                         "leak_rate": "gold word tokens not fully covered by any masked span (type-agnostic)",
                         "neg_fp_rate": "negative look-alike spans overlapped by any masked span",
                         "direct_view": f"gold types {sorted(INDIRECT_TYPES)} treated as ignore regions"},
            "systems": systems}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", type=Path, default=HERE / "dataset" / "it_pii_v1.jsonl")
    ap.add_argument("--predictions", type=Path, default=HERE / "results" / "predictions")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "summary.json")
    ap.add_argument("--reference", default="pseudora_generic_professional")
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    ap.add_argument("--subset", type=int, default=0)
    args = ap.parse_args()
    res = score_all(args.dataset, args.predictions, args.reference, args.bootstrap, args.subset)
    args.out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    for s, r in sorted(res["systems"].items(), key=lambda kv: -kv[1]["overall"]["lenient_f1"]):
        o = r["overall"]
        print(f"{s:32s} strictF1 {o['strict_f1']:.3f} lenF1 {o['lenient_f1']:.3f} leak {o['leak_rate']:.3f} "
              f"negFP {o['neg_fp_rate']:.3f} {r['meta']['ms_per_1k_chars']:7.1f} ms/1k")


if __name__ == "__main__":
    main()
