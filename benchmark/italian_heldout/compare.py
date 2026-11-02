"""Held-out vs original comparison tables and leak examples for the README.

Why: the point of the held-out corpus is the gap between the tuned corpus and unseen text; the
gap and the concrete leaks must be regenerated from committed predictions, not hand-copied.
What: reads results/summary.json (held-out), ../italian/results/summary.json (original), the
held-out gold and predictions; writes results/comparison.md and refreshes the block between the
markers in README.md: side-by-side headline metrics, overfitting gap, per-type and per-genre
leak, transformer cost/benefit, top leaking types with excerpts, and most-masked near-misses.
Test: CI re-runs it after re-scoring and fails on any drift (git diff --exit-code).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "italian"))
sys.path.insert(0, str(HERE.parent / "italian" / "systems"))
import score  # noqa: E402
from common import load_docs  # noqa: E402

RES, ORIG = HERE / "results", HERE.parent / "italian" / "results"
DATASET = HERE / "dataset" / "it_pii_heldout_v1.jsonl"
REF, MAX, NOTX = "pseudora_generic_professional", "pseudora_generic_professional_maximum", "ablation_regex_presidio"
PRE = "pseudora_presprint_generic_professional"
ROWS = [PRE, REF, MAX, NOTX, "ablation_regex", "presidio_vanilla_it", "rizzo_pii_only", "rizzo_default"]
# pre-sprint engine on it_pii_v1 (git show f790d04:benchmark/italian/results/summary.json); that run was replaced in results/
PRESPRINT_ORIG = {"overall": {"lenient_f1": 0.783, "strict_f1": 0.6681, "leak_rate": 0.2442, "neg_fp_rate": 0.1562},
                  "meta": {"ms_per_1k_chars": 330.99}}
MARK_START, MARK_END = "<!-- heldout:start -->", "<!-- heldout:end -->"
_WORD = re.compile(r"[^\W_]+")


def pct(x: float) -> str:
    return f"{100 * x:.1f}"


def ci(c: list[float]) -> str:
    return f"[{pct(c[0])}, {pct(c[1])}]"


def headline(H: dict, O: dict) -> list[str]:
    out = ["### Held-out vs original corpus\n",
           "| System | Lenient F1 held-out [95% CI] | original | Strict F1 held-out | original | Leak held-out [95% CI] | original "
           "| FP on negatives held-out [95% CI] | original | ms / 1k chars held-out | original |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in [r for r in ROWS if r in H]:
        h, hc, o = H[n]["overall"], H[n]["ci95"], O.get(n, {}).get("overall")
        oo = (lambda k: pct(o[k]) if o else "–")  # noqa: E731
        out.append(f"| `{n}` | **{pct(h['lenient_f1'])}** {ci(hc['lenient_f1'])} | {oo('lenient_f1')} | {pct(h['strict_f1'])} | {oo('strict_f1')} | "
                   f"**{pct(h['leak_rate'])}** {ci(hc['leak_rate'])} | {oo('leak_rate')} | {pct(h['neg_fp_rate'])} {ci(hc['neg_fp_rate'])} | "
                   f"{oo('neg_fp_rate')} | {H[n]['meta']['ms_per_1k_chars']} | {O[n]['meta']['ms_per_1k_chars'] if n in O else '–'} |")
    out += ["", "### Overfitting gap (held-out minus original, percentage points)\n",
            "| System | Δ lenient F1 | Δ strict F1 | Δ leak | Δ FP on negatives |", "|---|---|---|---|---|"]
    for n in [r for r in ROWS if r in H and r in O]:
        h, o = H[n]["overall"], O[n]["overall"]
        out.append(f"| `{n}` | {100 * (h['lenient_f1'] - o['lenient_f1']):+.1f} | {100 * (h['strict_f1'] - o['strict_f1']):+.1f} | "
                   f"{100 * (h['leak_rate'] - o['leak_rate']):+.1f} | {100 * (h['neg_fp_rate'] - o['neg_fp_rate']):+.1f} |")
    out += ["", f"### Paired difference vs `{REF}` on the held-out set (95% bootstrap CI, points)\n",
            "| System | Δ lenient F1 | Δ leak (positive = leaks more) |", "|---|---|---|"]
    for n in [r for r in ROWS if r in H and r != REF]:
        d = H[n]["ci95"]["delta_vs_reference"]
        out.append(f"| `{n}` | {ci(d['lenient_f1'])} | {ci(d['leak_rate'])} |")
    return out


def per_type(H: dict, O: dict) -> list[str]:
    cols = [r for r in (REF, MAX, NOTX, "rizzo_pii_only") if r in H]
    out = ["", "### Leak rate by entity type, held-out (original in parentheses for the reference)\n",
           "| Type (held-out gold spans) | " + " | ".join(f"`{c}`" for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    pt = H[REF]["per_type"]
    for t in sorted(pt, key=lambda t: -pt[t]["leak_rate"] * pt[t]["gold"]):
        orig = O[REF]["per_type"].get(t, {}).get("leak_rate")
        cells = [pct(H[c]["per_type"][t]["leak_rate"]) + (f" ({pct(orig)})" if c == REF and orig is not None else "") for c in cols]
        out.append(f"| {t} ({pt[t]['gold']}) | " + " | ".join(cells) + " |")
    out += ["", "### Held-out results by genre (lenient F1 / leak / FP on negatives)\n",
            "| Genre | " + " | ".join(f"`{c}`" for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for g in H[REF]["per_genre"]:
        cells = []
        for c in cols:
            v = H[c]["per_genre"][g]
            cells.append(f"– / – / {pct(v['neg_fp_rate'])}" if g == "negative" else
                         f"{pct(v['lenient_f1'])} / {pct(v['leak_rate'])} / {pct(v['neg_fp_rate'])}")
        out.append(f"| {g} | " + " | ".join(cells) + " |")
    out += ["", "### Hard cases on the held-out set (lenient recall)\n",
            "| Hard case (spans) | " + " | ".join(f"`{c}`" for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for h, v in sorted(H[REF]["hard_cases"].items(), key=lambda kv: kv[1]["lenient_recall"]):
        out.append(f"| {h} ({v['spans']}) | " + " | ".join(pct(H[c]["hard_cases"][h]["lenient_recall"]) for c in cols) + " |")
    return out


def excerpt(text: str, s: int, e: int, w: int = 45) -> str:
    a, b = max(0, s - w), min(len(text), e + w)
    frag = text[a:s] + "⟦" + text[s:e] + "⟧" + text[e:b]
    return ("…" if a else "") + frag.replace("\n", "⏎").replace("|", "¦").replace("`", "'") + ("…" if b < len(text) else "")


def leaks(system: str) -> list[str]:
    """What: for the 10 types with most leaked tokens, up to 2 excerpts each (fake data)."""
    docs = {d["id"]: d for d in load_docs(DATASET)}
    pred = json.loads((RES / "predictions" / f"{system}.json").read_text())["docs"]
    by_type, count = defaultdict(list), Counter()
    for doc_id, d in docs.items():
        cov = [False] * len(d["text"])
        for _, s, e in pred[doc_id]["spans"]:
            cov[s:e] = [True] * (e - s)
        for g in d["entities"]:
            toks = [m for m in _WORD.finditer(d["text"], g["start"], g["end"]) if m.group().casefold() not in score._LABEL_TOKENS]
            lost = [m for m in toks if not all(cov[m.start():m.end()])]
            if lost:
                count[g["type"]] += len(lost)
                by_type[g["type"]].append((len(lost) == len(toks), doc_id, g))
    out = ["", f"### Where `{system}` still leaks: top 10 types by leaked tokens (excerpts; all data is fake)\n",
           "⟦…⟧ marks the gold span; *full* = no token of it was masked, *partial* = some tokens were.\n",
           "| Type (leaked tokens) | Document | Excerpt |", "|---|---|---|"]
    for t, n in count.most_common(10):
        ex = sorted(by_type[t], key=lambda x: (not x[0], x[1]))[:2]
        for full, doc_id, g in ex:
            out.append(f"| {t} ({n}) | `{doc_id}` ({'full' if full else 'partial'}) | {excerpt(docs[doc_id]['text'], g['start'], g['end'])} |")
    fp = Counter()
    for doc_id, d in docs.items():
        for n_ in d["negatives"]:
            if any(score._overlap((n_["start"], n_["end"]), (s, e)) for _, s, e in pred[doc_id]["spans"]):
                fp[(n_["type"], d["text"][n_["start"]:n_["end"]].replace("\n", " "))] += 1
    out += ["", f"### Near-misses most often masked by `{system}` (should stay visible)\n", "| Look-alike | Text | Times masked |", "|---|---|---|"]
    out += [f"| {t} | {v} | {k} |" for (t, v), k in fp.most_common(12)]
    return out


def main() -> None:
    H = json.loads((RES / "summary.json").read_text())["systems"]
    O = {**json.loads((ORIG / "summary.json").read_text())["systems"], PRE: PRESPRINT_ORIG}
    md = "\n".join(headline(H, O) + per_type(H, O) + leaks(REF)) + "\n"
    (RES / "comparison.md").write_text(md)
    readme = HERE / "README.md"
    if readme.exists() and MARK_START in (text := readme.read_text()):
        head, rest = text.split(MARK_START, 1)
        readme.write_text(head + MARK_START + "\n" + md + MARK_END + rest.split(MARK_END, 1)[1])
    print(f"wrote {RES / 'comparison.md'}")


if __name__ == "__main__":
    main()
