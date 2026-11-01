"""OCR benchmark: s/page, pages/s with N workers, RAM, CER/WER on synthetic Italian A4 @300 DPI.

Run inside the test image (models baked in), CPU-limited like prod:
  docker run --rm --network none --cpus 4 --memory 4g <test-image> python bench/bench.py --workers 4
Prints one JSON object per configuration plus a Markdown table.
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "tests")]

from PIL import Image  # noqa: E402

from app.config import Settings  # noqa: E402
from app.inputs import PageImage  # noqa: E402
from app.main import build_engines  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from synth import cer_wer, degrade, make_page  # noqa: E402


def variants() -> dict[str, tuple[Image.Image, str]]:
    """Why/What: clean, noisy (blur+noise) and rotated (3 deg) A4 pages + reference text."""
    page = make_page(scribble=True)
    return {"clean": (page.image, page.text), "noisy": (degrade(page.image), page.text),
            "rotated": (page.image.rotate(-3, resample=3, fillcolor=255), page.text)}


def run(pipeline: Pipeline, engine: str, image: Image.Image) -> tuple[float, str, str]:
    """Why/What: one page through the full pipeline; returns (seconds, text, engine used)."""
    started = time.perf_counter()
    result = pipeline.ocr_page(PageImage(0, image, image.width, image.height, 300, 1.0), engine, "ita+eng", time.monotonic() + 600)
    return time.perf_counter() - started, " ".join(w.text for w in result.words), result.engine


def main() -> None:
    """Why: numbers for capacity planning (prod: 4 CPUs / 4 GiB). What: see module doc."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--throughput-pages", type=int, default=16)
    args = parser.parse_args()
    pages = variants()
    rows = []
    for label, variant, engine in (("tesseract-fast", "fast", "tesseract"), ("tesseract-best", "best", "tesseract"),
                                   ("rapidocr", "fast", "rapidocr"), ("auto (fast)", "fast", "auto")):
        settings = Settings(tessdata_variant=variant, workers=args.workers)
        pipeline = Pipeline(settings, build_engines(settings))
        run(pipeline, engine, pages["clean"][0])  # warm-up (ONNX session init, page cache)
        row: dict[str, object] = {"config": label}
        for name, (image, reference) in pages.items():
            timings = []
            for _ in range(args.repeat):
                seconds, text, used = run(pipeline, engine, image)
                timings.append(seconds)
            cer, wer = cer_wer(reference, text)
            row[f"{name}_s"] = round(sorted(timings)[len(timings) // 2], 2)
            row[f"{name}_cer"], row[f"{name}_wer"] = round(cer * 100, 2), round(wer * 100, 2)
            row[f"{name}_engine"] = used
        mixed = [pages[k][0] for k in ("clean", "noisy", "rotated")] * (args.throughput_pages // 3 + 1)
        mixed = mixed[: args.throughput_pages]
        started = time.perf_counter()
        with ThreadPoolExecutor(args.workers) as pool:
            list(pool.map(lambda img: run(pipeline, engine, img), mixed))
        row["pages_per_s"] = round(len(mixed) / (time.perf_counter() - started), 2)
        rows.append(row)
        print(json.dumps(row), flush=True)
    # RUSAGE_CHILDREN is useless here: Linux keeps the parent's pre-exec high-water mark. Per-process
    # RAM under load is measured by bench/mem_probe.py against the running service instead.
    print(json.dumps({"peak_rss_bench_process_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}))
    print("\n| config | clean s/page | noisy s/page | rotated s/page | pages/s (%d workers) | CER clean/noisy/rotated %% | WER clean/noisy/rotated %% |" % args.workers)
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['config']} | {r['clean_s']} | {r['noisy_s']} | {r['rotated_s']} | {r['pages_per_s']} | "
              f"{r['clean_cer']}/{r['noisy_cer']}/{r['rotated_cer']} | {r['clean_wer']}/{r['noisy_wer']}/{r['rotated_wer']} |")


if __name__ == "__main__":
    main()
