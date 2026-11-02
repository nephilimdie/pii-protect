"""Build (or verify) the frozen held-out corpus it_pii_heldout_v1.

Why: the corpus must be byte-for-byte reproducible and frozen by hash before any system runs.
What: renders every template in templates_formal / templates_informal / templates_negative with a
per-document string seed, writes dataset/it_pii_heldout_v1.jsonl and .stats.json (sha256 inside);
--check regenerates in memory and fails on any difference with the committed files.
Test: `python3 build.py --check` exits 0; tests/test_heldout.py does the same in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from markup import Ctx, render  # noqa: E402
from templates_formal import FORMAL  # noqa: E402
from templates_informal import INFORMAL  # noqa: E402
from templates_negative import NEGATIVE  # noqa: E402

VERSION = "it_pii_heldout_v1"
DATASET = HERE / "dataset" / f"{VERSION}.jsonl"
UPPER_FORMS = {"verbale", "cu", "f24", "referto", "busta_paga"}  # all-caps typed forms occur in these


def generate() -> list[dict]:
    docs = []
    for genre, subs in {**FORMAL, **INFORMAL, **NEGATIVE}.items():
        for sub, fn, n, ocr_p in subs:
            for i in range(1, n + 1):
                rng = random.Random(f"{VERSION}:{sub}:{i}")
                ocr = rng.random() < ocr_p
                case = "upper" if sub in UPPER_FORMS and rng.random() < .1 else None
                c = Ctx(rng, ocr=ocr, case=case)
                docs.append(render(c, fn(c), f"{sub}-{i:03d}", genre, sub, ("all_caps_doc",) if case else ()))
    return docs


def payload(docs: list[dict]) -> str:
    return "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)


def stats(docs: list[dict], text: str) -> dict:
    ents = [e for d in docs for e in d["entities"]]
    return {"version": VERSION, "documents": len(docs), "characters": sum(len(d["text"]) for d in docs),
            "by_genre": dict(Counter(d["genre"] for d in docs)), "by_subgenre": dict(Counter(d["subgenre"] for d in docs)),
            "documents_without_pii": sum(not d["entities"] for d in docs),
            "pii_spans": len(ents), "pii_by_type": dict(Counter(e["type"] for e in ents).most_common()),
            "negative_spans": sum(len(d["negatives"]) for d in docs),
            "negatives_by_type": dict(Counter(n["type"] for d in docs for n in d["negatives"]).most_common()),
            "ignore_spans": sum(len(d["ignore"]) for d in docs),
            "hard_case_spans": dict(Counter(h for e in ents for h in e.get("hard", ())).most_common()),
            "ocr_documents": sum("ocr" in d["tags"] for d in docs),
            "sha256": hashlib.sha256(text.encode()).hexdigest()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    docs = generate()
    text = payload(docs)
    st = stats(docs, text)
    if args.check:
        ok = DATASET.read_text(encoding="utf-8") == text and json.loads(DATASET.with_suffix(".stats.json").read_text()) == st
        print("OK" if ok else "DRIFT", st["sha256"])
        raise SystemExit(0 if ok else 1)
    DATASET.parent.mkdir(exist_ok=True)
    DATASET.write_text(text, encoding="utf-8")
    DATASET.with_suffix(".stats.json").write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: st[k] for k in ("documents", "pii_spans", "negative_spans", "documents_without_pii", "sha256")}))


if __name__ == "__main__":
    main()
