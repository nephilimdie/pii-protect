"""Visual PII benchmark: ms/image per detector (face, code, plate, all), 4-worker throughput, RAM.

Run inside the test image (models baked in), CPU-limited like prod:
  docker run --rm --network none --cpus 4 --memory 4g <test-image> python bench/visual_bench.py
Prints one JSON object per (scene, detectors) and the process peak RSS.
"""
from __future__ import annotations

import json
import resource
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "tests")]

from PIL import Image  # noqa: E402

from app.config import Settings  # noqa: E402
from app.inputs import PageImage  # noqa: E402
from app.main import build_detectors, build_engines  # noqa: E402
from app.visual import VisualPipeline  # noqa: E402
from synth import make_page  # noqa: E402
from test_visual import mona, plate_image, qr_image  # noqa: E402


def scenes() -> dict[str, Image.Image]:
    """Why/What: a 1200x800 photo (face + QR + plate), a 4000x3000 photo (tiled faces), an A4 scan."""
    photo, _ = plate_image()
    photo.paste(mona().resize((165, 246)), (900, 60))
    photo.paste(qr_image(scale=5, border=4), (60, 300))
    big = Image.new("RGB", (4000, 3000), (120, 130, 140))
    for x in range(200, 3800, 900):
        big.paste(mona().resize((110, 164)), (x, 1400))
    scan = make_page().image.convert("RGB")
    scan.paste(mona().resize((500, 745)), (1800, 200))
    return {"photo_1200x800": photo, "photo_4000x3000": big, "scan_a4_300dpi": scan}


def timed(pipeline: VisualPipeline, image: Image.Image, wanted: tuple[str, ...]) -> tuple[float, int]:
    """Why/What: one image through the visual pipeline; returns (ms, boxes)."""
    started = time.perf_counter()
    result = pipeline.run(PageImage(0, image, image.width, image.height, 300, 1.0), wanted, time.monotonic() + 600)
    return (time.perf_counter() - started) * 1000, len(result.boxes)


def main() -> None:
    settings = Settings()
    pipeline = VisualPipeline(settings, build_detectors(settings), build_engines(settings))
    for name, image in scenes().items():
        for wanted in (("face",), ("code",), ("plate",), ("face", "code", "plate")):
            timed(pipeline, image, wanted)  # warm-up (ONNX session, first OCR)
            runs = [timed(pipeline, image, wanted) for _ in range(3)]
            print(json.dumps({"scene": name, "detectors": ",".join(wanted), "boxes": runs[0][1],
                              "median_ms": round(statistics.median(r[0] for r in runs))}), flush=True)
    photo = scenes()["photo_1200x800"]
    started = time.perf_counter()
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: timed(pipeline, photo, ("face", "code", "plate")), range(16)))
    print(json.dumps({"throughput_images_per_s_4_workers": round(16 / (time.perf_counter() - started), 2),
                      "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}))


if __name__ == "__main__":
    main()
