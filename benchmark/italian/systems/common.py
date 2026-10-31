"""Shared prediction I/O for every benchmarked system (host side and inside containers).

Why: all systems must emit the same offsets-only format so score.py treats them identically.
What: load_docs() reads the gold JSONL; run_system() times a detect(text) callable per
document and writes {system, family, meta, docs: {id: {spans: [[label, start, end]], ms}}}.
Test: tests/test_italian_bench.py runs run_system with a fake detector and re-loads the file.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Callable

Span = tuple[str, int, int]


def load_docs(path: str | Path, subset: int = 0) -> list[dict]:
    """What: gold documents; subset=k keeps the first k documents of every sub-genre (stratified)."""
    docs = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    seen: Counter = Counter()
    out = []
    for d in docs:
        if not subset or seen[d["subgenre"]] < subset:
            seen[d["subgenre"]] += 1
            out.append(d)
    return out


def run_system(docs: list[dict], detect: Callable[[str], list[Span]], out: str | Path,
               system: str, family: str, meta: dict) -> None:
    """Why: identical timing and validation for every system.
    What: calls detect on each text (one warm-up call first), validates offsets, writes JSON.
    Test: a detector returning [('PERSON', 0, 5)] yields that span for every document.
    """
    detect(docs[0]["text"])
    rows = {}
    for d in docs:
        started = time.perf_counter()
        spans = detect(d["text"])
        ms = (time.perf_counter() - started) * 1000
        for label, s, e in spans:
            if not (isinstance(label, str) and 0 <= s < e <= len(d["text"])):
                raise ValueError(f"{system}: invalid span {label, s, e} in {d['id']}")
        rows[d["id"]] = {"spans": [list(x) for x in sorted(spans, key=lambda x: (x[1], x[2], x[0]))], "ms": round(ms, 2)}
    Path(out).write_text(json.dumps({"system": system, "family": family, "meta": meta, "docs": rows},
                                    sort_keys=True, separators=(",", ":")) + "\n")
    print(f"{system}: {len(rows)} docs -> {out}", flush=True)
