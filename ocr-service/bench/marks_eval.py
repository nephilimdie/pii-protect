"""Signature/stamp detector precision, recall and cost on procedural forms (run inside the test image).

    python bench/marks_eval.py [n_seeds] [first_seed]   # tuned on seeds 0-7; report held-out seeds

A truth mark counts as found when a predicted box of the same type covers >= 90% of it; a
prediction is a false positive when it overlaps no truth mark. Printed text, tables and logos
are on every page, so every false positive there is a precision miss.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "tests")]

from app.config import Settings  # noqa: E402
from app.inputs import PageImage  # noqa: E402
from app.main import build_engines  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from synth import make_page  # noqa: E402
from synth_marks import make_form, scan  # noqa: E402


def covered(truth: tuple[int, int, int, int], box: tuple[int, int, int, int]) -> float:
    w = max(0, min(truth[2], box[2]) - max(truth[0], box[0]))
    h = max(0, min(truth[3], box[3]) - max(truth[1], box[1]))
    return w * h / max(1, (truth[2] - truth[0]) * (truth[3] - truth[1]))


def main(seeds: int, start: int = 0) -> None:
    dpi = int(os.environ.get("MARKS_DPI", "200"))
    settings = Settings(internal_api_key="bench")
    pipeline = Pipeline(settings, build_engines(settings))
    variants = [
        ("round red, blue sig, colour", dict(stamp="round", stamp_ink="red", sig_ink="blue"), False),
        ("oval violet, black sig, colour", dict(stamp="oval", stamp_ink="violet", sig_ink="black"), False),
        ("rect blue, blue sig, colour", dict(stamp="rect", stamp_ink="blue", sig_ink="blue"), False),
        ("round, black sig, grey scan", dict(stamp="round", stamp_ink="black", sig_ink="black"), True),
        ("sig without label, no stamp", dict(stamp=None, label=False), False),
        ("no marks (text/table/logo)", dict(stamp=None, signature=False), False),
    ]
    stats: dict[str, list[int]] = {"SIGNATURE": [0, 0, 0], "STAMP": [0, 0, 0]}  # tp, fn, fp
    reviewed = {"SIGNATURE": 0, "STAMP": 0}
    timings: list[float] = []
    for name, kwargs, gray in variants:
        row = {"SIGNATURE": [0, 0, 0], "STAMP": [0, 0, 0]}
        for seed in range(start, start + seeds):
            form = make_form(seed=seed, dpi=dpi, **kwargs)  # type: ignore[arg-type]
            image = scan(form.image, seed, gray=gray)
            page = PageImage(0, image, image.width, image.height, dpi, 1.0)
            started = time.perf_counter()
            plain = pipeline.ocr_page(page, "auto", "ita+eng", time.monotonic() + 120)
            base = time.perf_counter() - started
            started = time.perf_counter()
            result = pipeline.ocr_page(page, "auto", "ita+eng", time.monotonic() + 120, ("signature", "stamp"))
            timings.append((time.perf_counter() - started) - base)
            del plain
            for kind, truth in form.truth:
                hit = any(m.type == kind and covered(truth, m.bbox) >= 0.9 for m in result.marks)
                row[kind][0 if hit else 1] += 1
            for mark in result.marks:
                if not any(covered(mark.bbox, truth) > 0 or covered(truth, mark.bbox) > 0 for _, truth in form.truth):
                    row[mark.type][2] += 1
                reviewed[mark.type] += mark.needs_review
        for kind in row:
            stats[kind] = [a + b for a, b in zip(stats[kind], row[kind])]
        print(f"{name:34s} SIG tp/fn/fp {row['SIGNATURE']}  STAMP tp/fn/fp {row['STAMP']}")
    letters_fp = 0
    for seed in range(start, start + seeds):
        page_img = scan(make_page(dpi=dpi).image.convert("RGB"), seed)
        result = pipeline.ocr_page(PageImage(0, page_img, page_img.width, page_img.height, dpi, 1.0), "auto",
                                   "ita+eng", time.monotonic() + 120, ("signature", "stamp"))
        letters_fp += len(result.marks)
    print(f"{'plain letter (no marks)':34s} false positives {letters_fp}")
    for kind, (tp, fn, fp) in stats.items():
        fp_total = fp + (letters_fp if kind == "SIGNATURE" else 0)
        print(f"{kind}: recall {tp / max(1, tp + fn):.2%} ({tp}/{tp + fn}), precision "
              f"{tp / max(1, tp + fp):.2%} (fp {fp}), needs_review {reviewed[kind]}")
    timings.sort()
    print(f"marks cost per A4 page @{dpi}dpi: median {timings[len(timings) // 2] * 1000:.0f} ms, "
          f"max {timings[-1] * 1000:.0f} ms (n={len(timings)})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5, int(sys.argv[2]) if len(sys.argv) > 2 else 0)
