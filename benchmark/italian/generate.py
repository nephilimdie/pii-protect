"""Deterministic generator of the synthetic Italian PII benchmark (gold span annotations).

Why: an honest benchmark needs many varied documents with exact gold offsets, hard cases
and non-PII look-alikes; hand annotation does not scale and real documents cannot be shared.
What: builds documents from genre templates; every PII value, negative look-alike and
"ignore" region is recorded with Python str offsets while the text is assembled.
Test: `python3 generate.py --check` regenerates and verifies offsets/stats; the unit tests
assert determinism (same seed -> same SHA-256) and that every span slices to its value.

Usage: python3 benchmark/italian/generate.py [--seed 20261026] [--out dataset/it_pii_v1.jsonl]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from gold import NEG_TYPES, PII_TYPES, Doc  # noqa: F401  (types re-exported for scorers)
from templates import GENRES

VERSION = "it_pii_v1"
SEED = 20261026
HERE = Path(__file__).resolve().parent


def generate(seed: int = SEED) -> list[dict]:
    """Why: single deterministic entry point for CLI, tests and CI.
    What: returns all documents; ~10% of non-log documents get OCR-like noise.
    Test: generate(1) == generate(1) and len(generate()) >= 600.
    """
    rng = random.Random(seed)
    docs = []
    for genre, subs in GENRES.items():
        for sub, fn, count in subs:
            for k in range(count):
                drng = random.Random(rng.getrandbits(64))
                ocr = genre not in ("logs_json", "chat_prompt", "negative") and drng.random() < .12
                d = Doc(drng, genre, sub, ocr=ocr)
                fn(d)
                docs.append(d.build(f"{genre}-{sub}-{k + 1:03d}"))
    return docs


def stats(docs: list[dict]) -> dict:
    return {
        "version": VERSION, "documents": len(docs), "characters": sum(len(d["text"]) for d in docs),
        "by_genre": dict(Counter(d["genre"] for d in docs)),
        "pii_spans": sum(len(d["entities"]) for d in docs),
        "pii_by_type": dict(Counter(e["type"] for d in docs for e in d["entities"]).most_common()),
        "negative_spans": sum(len(d["negatives"]) for d in docs),
        "negatives_by_type": dict(Counter(e["type"] for d in docs for e in d["negatives"]).most_common()),
        "ignore_spans": sum(len(d["ignore"]) for d in docs),
        "hard_case_spans": dict(Counter(h for d in docs for e in d["entities"] for h in e.get("hard", [])).most_common()),
        "ocr_documents": sum("ocr" in d["tags"] for d in docs),
        "documents_without_pii": sum(not d["entities"] for d in docs),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=HERE / "dataset" / f"{VERSION}.jsonl")
    ap.add_argument("--check", action="store_true", help="verify the committed file matches the generator")
    args = ap.parse_args()
    docs = generate(args.seed)
    payload = "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    if args.check:
        current = args.out.read_text(encoding="utf-8")
        assert current == payload, f"{args.out} differs from generator output (seed {args.seed})"
        print("dataset matches generator", digest)
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload, encoding="utf-8")
    st = {**stats(docs), "seed": args.seed, "sha256": digest}
    args.out.with_suffix(".stats.json").write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(st, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
