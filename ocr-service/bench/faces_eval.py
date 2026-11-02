"""Face recall on licence-clean variants (PD Mona Lisa: tilted, small, squeezed = yaw-like) and
false positives on documents (procedural forms, a letter, the own-work form photo).

    python bench/faces_eval.py [threshold ...]
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "tests")]

from PIL import Image  # noqa: E402

from app.config import Settings  # noqa: E402
from app.detectors.faces import YuNet  # noqa: E402
from synth import make_page  # noqa: E402
from synth_marks import make_form, scan  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
FACE = (125, 85, 190, 170)  # eyes to chin on mona_lisa_330.jpg


def variants() -> list[tuple[str, Image.Image, tuple[float, float, float, float]]]:
    """(name, image, true face box) built from the public-domain portrait."""
    mona = Image.open(FIX / "mona_lisa_330.jpg").convert("RGB")
    out = [("upright", mona, FACE)]
    for angle in (15, -15, 25, -25, 35, -35, 45, -50, 60, -60, 75):
        turned = mona.rotate(angle, expand=True, fillcolor=(200, 200, 195), resample=Image.Resampling.BICUBIC)
        cx, cy, tx, ty = mona.width / 2, mona.height / 2, turned.width / 2, turned.height / 2
        a = math.radians(angle)
        pts = [(x - cx, y - cy) for x in (FACE[0], FACE[2]) for y in (FACE[1], FACE[3])]
        mapped = [(tx + math.cos(a) * x + math.sin(a) * y, ty - math.sin(a) * x + math.cos(a) * y) for x, y in pts]
        out.append((f"tilt {angle:+d}", turned, (min(p[0] for p in mapped), min(p[1] for p in mapped),
                                                 max(p[0] for p in mapped), max(p[1] for p in mapped))))
    for squeeze in (0.6, 0.45):  # yaw-like: the face narrows as the head turns
        narrow = mona.resize((round(mona.width * squeeze), mona.height))
        out.append((f"yaw-like x{squeeze}", narrow, (FACE[0] * squeeze, FACE[1], FACE[2] * squeeze, FACE[3])))
    for canvas_side, face_px in ((900, 28), (1200, 24), (1600, 30), (3000, 26), (800, 40), (900, 16), (700, 14), (1000, 18), (1280, 15), (2000, 14)):
        f = face_px / (FACE[2] - FACE[0])
        small = mona.resize((max(1, round(mona.width * f)), max(1, round(mona.height * f))))
        scene = Image.new("RGB", (canvas_side, round(canvas_side * 0.66)), (225, 228, 230))
        x, y = round(canvas_side * 0.6), round(canvas_side * 0.3)
        scene.paste(small, (x, y))
        out.append((f"small {face_px}px in {canvas_side}", scene,
                    (x + FACE[0] * f, y + FACE[1] * f, x + FACE[2] * f, y + FACE[3] * f)))
    from PIL import ImageEnhance, ImageFilter
    dim = ImageEnhance.Contrast(mona.filter(ImageFilter.GaussianBlur(2))).enhance(0.4)
    out.append(("blurred low-contrast", dim, FACE))
    scene = Image.new("RGB", (900, 600), (120, 120, 120))
    scene.paste(dim.rotate(30, expand=True, fillcolor=(120, 120, 120)).resize((140, 160)), (500, 200))
    out.append(("small tilted dim", scene, (500 + 0.3 * 140, 200 + 0.15 * 160, 500 + 0.75 * 140, 200 + 0.55 * 160)))
    return out


def documents() -> list[tuple[str, Image.Image]]:
    docs = [(f"form {s}", scan(make_form(seed=s, dpi=200).image, s)) for s in range(4)]
    docs.append(("letter", make_page(dpi=200).image.convert("RGB")))
    docs.append(("form photo", Image.open(FIX / "form_photo.jpg").convert("RGB")))
    return docs


def covered(truth, box) -> float:  # type: ignore[no-untyped-def]
    w = max(0, min(truth[2], box[2]) - max(truth[0], box[0]))
    h = max(0, min(truth[3], box[3]) - max(truth[1], box[1]))
    return w * h / ((truth[2] - truth[0]) * (truth[3] - truth[1]))


def main(thresholds: list[float]) -> None:
    settings = Settings(internal_api_key="bench")
    faces, docs = variants(), documents()
    for threshold in thresholds:
        model = YuNet(settings.face_model_path, threshold, settings.face_review_score, settings.face_review_side)
        found, ms = 0, []
        print(f"threshold {threshold}")
        for name, image, truth in faces:
            started = time.perf_counter()
            hits = model.detect(image)
            ms.append((time.perf_counter() - started) * 1000)
            ok = [h for h in hits if covered(truth, h.bbox) >= 0.9]
            found += bool(ok)
            extra = len(hits) - len(ok)
            print(f"  {name:22s} {'FOUND' if ok else 'miss '} "
                  f"{('score %.2f review %s' % (ok[0].score, ok[0].needs_review)) if ok else ''} extra={extra}")
        fps = 0
        for name, image in docs:
            hits = model.detect(image)
            fps += len(hits)
            if hits:
                print(f"  FP on {name}: {[(round(h.score, 2), [round(c) for c in h.bbox]) for h in hits]}")
        print(f"  recall {found}/{len(faces)}, false positives on {len(docs)} documents: {fps}, "
              f"median {sorted(ms)[len(ms) // 2]:.0f} ms/image")


if __name__ == "__main__":
    main([float(a) for a in sys.argv[1:]] or [0.6, 0.5, 0.45])
