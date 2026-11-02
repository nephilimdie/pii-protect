# OCR service (internal)

FastAPI microservice that turns scanned PDFs and images into words with pixel boxes, for the
engine's document redaction. Contract: [`openapi.yaml`](openapi.yaml). Not exposed publicly.

- Engines: **Tesseract 5** (`ita+eng`, LSTM, `tessdata_fast` default or `tessdata_best`) and
  **PP-OCRv4 mobile** ONNX models (RapidOCR's Apache-2.0 model files, run by our own small
  numpy/onnxruntime runner because the `rapidocr_onnxruntime` package hard-depends on
  `opencv-python`, whose wheels bundle LGPL FFmpeg/Qt).
- PDF rendering: **pypdfium2** (no PyMuPDF/AGPL).
- `engine=auto` (default): Tesseract + adaptive preprocessing (contrast/denoise, local
  binarisation, 1.5x upscale) while mean confidence < 80, RapidOCR competes below 70.
- Every page: EXIF orientation, Tesseract OSD 90/180/270 turn for low-confidence pages without
  EXIF/PDF rotation (`osd.traineddata`, Apache-2.0; `OCR_OSD_MIN_CONFIDENCE`, default 2),
  projection-profile deskew (+/-10 deg), boxes mapped back to the
  page frame as over-covering envelopes, `low_conf_regions` (conf < 60) and
  `ink_without_text_regions` (signatures, stamps, handwriting, pictures).

## Guarantees

| Concern | How |
|---|---|
| RAM-only | body read with a hard cap, multipart spool limit above the cap (no temp file), PDF/images decoded from bytes, Tesseract via stdin/stdout; `TMPDIR=/dev/shm`; test asserts zero file writes for a 3 MB upload |
| No egress | models baked in at build time (sha256-pinned); compose `internal: true` network; CI runs tests with `--network none`; test patches sockets |
| No content in logs | logs carry status/engine/duration and exception *types* only; test asserts filename/content absent |
| No caching | `Cache-Control: no-store` + `nosniff` on every response |
| Fail-closed | any page failure -> whole request 5xx with flat `{"error","message"}`; deadline -> 504 (Tesseract killed) |
| Bounded | file size, pages per request (no truncation), pixels per page (adaptive DPI, floor 100), input pixels, timeout, `OCR_WORKERS` semaphore -> `503 BUSY` + `Retry-After` |
| Auth | `X-Internal-Key` (constant-time compare); empty key -> 503, readiness not ready |

Known limitation: RapidOCR's detector can read a scribble/signature as a confident "word". Its
word confidence is therefore the *weakest character* probability, and `auto`/`tesseract`
(Tesseract reports such ink as `ink_without_text_regions`) are the recommended modes.
Rotations of 90/180 deg without EXIF are not detected (only skew up to `OCR_MAX_SKEW_DEGREES`).
The PP-OCRv4 alphabet lacks some Italian accented letters (`à` -> `a`).

## Configuration (env, prefix `OCR_`)

| Var | Default | |
|---|---|---|
| `INTERNAL_API_KEY` | (empty = refuse) | shared secret with the engine |
| `WORKERS` | 4 | concurrent OCR jobs (one CPU each) |
| `BUSY_TIMEOUT_SECONDS` / `RETRY_AFTER_SECONDS` | 1 / 5 | queue wait before 503 BUSY |
| `TIMEOUT_SECONDS` | 120 | per request |
| `MAX_FILE_BYTES` / `MAX_PAGES` | 20 MB / 20 | |
| `MAX_PAGE_PIXELS` / `MAX_INPUT_PIXELS` | 20 MP / 100 MP | A4 @300 DPI = 8.7 MP |
| `DEFAULT_DPI` / `MIN_DPI` / `MAX_DPI` | 300 / 100 / 600 | |
| `TESSDATA_VARIANT` | `fast` | `best` = 2x slower, no gain (benchmark below) |
| `LOW_CONF_THRESHOLD` / `ADAPTIVE_CONF_THRESHOLD` / `AUTO_FALLBACK_CONF` | 60 / 80 / 70 | |
| `MAX_PASSES` / `MAX_SKEW_DEGREES` | 3 / 10 | |
| `FACE_MODEL_PATH` | `/opt/ocr-models/yunet/face_detection_yunet_2023mar.onnx` | missing = readiness 503, `face` requests 503 |
| `FACE_THRESHOLD` / `FACE_REVIEW_SCORE` / `FACE_REVIEW_SIDE` | 0.6 / 0.8 / 32 px | recall-oriented; below review score or side -> `needs_review` |
| `PLATE_REVIEW_CONF` / `VISUAL_MAX_SIDE` | 80 / 4000 px | |

## Visual PII (`POST /v1/visual-pii`)

One image or PDF page per call; `detectors=face,code,plate` (default all). Returns
`{width, height, boxes: [{type, bbox, score, needs_review}]}` in the same frame as `/v1/ocr`.
- **FACE**: YuNet ONNX (OpenCV Zoo, MIT) on onnxruntime with our own pre/post-processing and NMS
  (no OpenCV wheel). Whole image + 640 px tiles (128 px overlap, at most 2560 px) for small faces in
  large photos. Boxes grown 15 % x / 20 % y (hair, ears). Profile (nose off eye midline), small or
  low-score faces are `needs_review`.
- **QR_CODE / BARCODE**: zxing-cpp (rotation, inversion, downscale). Positions only: content never
  returned or logged. Undecodable symbols zxing can still locate are returned with `needs_review`.
- **LICENSE_PLATE**: Italian formats (AA 000 AA; moto AA 00000 and pre-1994 provincial -> review)
  matched on RapidOCR words, box grown to the plate border. Plates OCR cannot read are missed.

Local timings (Apple M-series, docker, 2 CPUs): face 330x492 16 ms, face 3000x2000 tiled 0.3 s,
face+code on A4@300 dpi 0.37 s, code 1600x1000 15 ms, face+code+plate 1200x800 0.3 s.

## Visual PII benchmark (prod host, 2026-11-01)

Same throwaway setup (`--cpus 4 --memory 4g --network none`), `python bench/visual_bench.py`,
median of 3 after a warm-up, ms per image (boxes found in brackets):

| scene | face | code | plate | all three |
|---|---|---|---|---|
| photo 1200x800 (face, QR, plate) | 174 (1) | 19 (1) | 594 (1) | 781 (3) |
| photo 4000x3000 (4 small faces, tiled) | 851 (4) | 381 (1 false, review) | 1994 (0) | 2922 (5) |
| A4 scan @300 DPI (ID photo) | 672 (1) | 213 (0) | 3291 (0) | 4219 (1) |

4 concurrent photos 1200x800 (all detectors): 3.87 images/s. RAM: peak 1.39 GiB (`docker stats`,
1 s samples; RSS 1.46 GiB), dominated by the RapidOCR sessions the plate detector shares with
`/v1/ocr`, so it fits the existing `mem_limit: 4g`. The plate detector is a second full RapidOCR
pass, so the engine skips it on scanned PDF pages (their plate text is already in the OCR text).
False positive seen: zxing reads a row of identical pictures as a barcode (score 0.5,
`needs_review`): it causes over-redaction only.

## Benchmark (prod host, 2026-11-01)

Throwaway container on the prod host (12 vCPU, load ~0.4), `--cpus 4 --memory 4g --network none`,
`OCR_WORKERS=4`, synthetic Italian A4 @300 DPI (2480x3508) with a signature scribble; noisy =
blur + noise, rotated = 3 deg. Median of 3 runs, full pipeline (deskew, adaptive passes, regions).
`python bench/bench.py --workers 4` and `bench/mem_probe.py`.

| config | clean s/page | noisy s/page | rotated s/page | pages/s (4 CPU, 4 workers) | CER % clean/noisy/rot | WER % clean/noisy/rot |
|---|---|---|---|---|---|---|
| tesseract fast | 2.64 | 2.61 | 3.87 | 0.99 | 0.49 / 0.49 / 0.87 | 1.85 / 1.85 / 1.85 |
| tesseract best | 5.56 | 5.02 | 6.10 | 0.63 | 0.62 / 0.62 / 0.99 | 1.85 / 1.85 / 1.85 |
| rapidocr (PP-OCRv4 mobile) | 4.64 | 5.12 | 5.12 | 0.53 | 1.73 / 1.48 / 1.98 | 9.26 / 9.26 / 8.33 |
| **auto** (fast, default) | 2.66 | 2.44 | 3.35 | **1.14** | 0.49 / 0.49 / 0.87 | 1.85 / 1.85 / 1.85 |

RAM (container, `docker stats`): idle 87 MiB; peak under 4 concurrent pages: tesseract 572 MiB,
rapidocr 1.68 GiB, auto 1.87 GiB (ONNX sessions stay loaded: 1.55 GiB afterwards). One tesseract
process peaks at 91 MiB (VmHWM). So ~140 MiB per Tesseract worker, ~400 MiB per RapidOCR worker
plus ~1.2 GiB shared ONNX/arena; `mem_limit: 4g` leaves ~2x headroom at 4 workers.
`tessdata_best` doubles latency for no accuracy gain on these pages -> `fast` stays the default.
Capacity: ~1 page/s per 4 CPUs, i.e. a 20-page scan ~18-20 s of wall time when the service is idle.

## Run / test

```sh
docker build --target runtime -t pseudora-ocr .
docker build --target test -t pseudora-ocr-test . && docker run --rm --network none --read-only \
  --tmpfs /dev/shm:rw,size=256m --tmpfs /tmp:rw,size=16m pseudora-ocr-test
# local venv: sh scripts/fetch_models.sh /tmp/ocr-models
#   OCR_TESSDATA_ROOT=/tmp/ocr-models/tessdata OCR_RAPIDOCR_MODEL_DIR=/tmp/ocr-models/rapidocr pytest -q
```

Engine dev compose: `docker compose --profile ocr up` (service `ocr`, network `ocr_internal`).

### Production compose snippet (cloud repo; not applied from here)

```yaml
services:
  ocr:
    image: ghcr.io/<org>/pseudora-ocr:<tag>      # built from ocr-service/ (target runtime)
    environment:
      OCR_INTERNAL_API_KEY: ${OCR_INTERNAL_API_KEY:?set me}
      OCR_WORKERS: "4"
      OCR_TESSDATA_VARIANT: fast
    networks: [ocr_internal]                    # no published ports
    read_only: true
    tmpfs:
      - /dev/shm:rw,noexec,nosuid,size=512m
      - /tmp:rw,noexec,nosuid,size=16m
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    cpus: 4
    mem_limit: 4g
    pids_limit: 256
    restart: unless-stopped
  api:
    networks: [default, ocr_internal]
networks:
  ocr_internal:
    internal: true                              # no route to the internet
```

## Dependencies and licences

| Component | Licence |
|---|---|
| fastapi, pydantic, pydantic-settings, anyio | MIT |
| starlette, uvicorn, numpy | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| pypdfium2 (+ PDFium) | Apache-2.0 / BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| onnxruntime | MIT |
| Tesseract 5, Leptonica | Apache-2.0, BSD-2-Clause |
| tessdata_fast / tessdata_best 4.1.0 (ita, eng) | Apache-2.0 |
| PP-OCRv4 mobile det/rec ONNX (from rapidocr_onnxruntime 1.4.4 wheel, models only) | Apache-2.0 |
| zxing-cpp 3.1.1 | Apache-2.0 |
| YuNet `face_detection_yunet_2023mar.onnx` (opencv_zoo @48b10fa, weights + model card) | MIT |
| test only: pytest, httpx, segno, python-barcode | MIT, BSD-3-Clause, BSD-3-Clause, MIT |
| test fixture `tests/fixtures/mona_lisa_330.jpg` | public domain (see tests/fixtures/README.md) |

Base image `python:3.12-slim-bookworm` (Debian; system libraries such as glibc are LGPL and
dynamically linked, as in every Debian image).

## Signatures and stamps (`marks`), face recall (phase 4)

`POST /v1/ocr` with `marks=signature,stamp` also returns `pages[].marks` (SIGNATURE / STAMP boxes,
padded). No model is used: no signature/stamp detector with a permissive licence for both code and
weights was found (the public ones are YOLO/Ultralytics, AGPL, or have no weight licence). It is a
heuristic (`app/detectors/marks.py`, numpy + Pillow) over the same ink mask as
`ink_without_text_regions` and the page's own OCR words:

- SIGNATURE: ink left after removing confident words, grouped by a ~2.5 mm dilation; 3-60 mm tall,
  8-180 mm wide, sparse, thin strokes, curvy (gradient-orientation entropy >= 0.75). Confident when
  next to a label (Firma, Firmato, F.to, In fede, Il dichiarante, Signature); unlabelled ink must
  also be one connected, wide stroke group and is `needs_review`.
- STAMP: a ring (round/oval, 12-70 mm, outer band covering >= 80% of the angles, sparse inside)
  in any ink, or a coloured (red/blue/violet) axis-aligned frame: confident. A compact, sparse
  coloured group that is not printed text, or one near "Timbro": `needs_review`.
- Hits are only added, never replaced, so a signature across a stamp keeps both boxes.

Procedural fixtures (`tests/synth_marks.py`: Bezier signatures with pressure variation, Pillow
stamps with worn ink, forms with text, a table and a logo). `bench/marks_eval.py`, tuned on seeds
0-7 and reported on held-out seeds:

| set | SIGNATURE recall / precision | STAMP recall / precision |
|---|---|---|
| 120 pages @200 dpi (seeds 100-119) | 98% / 100% | 100% / 98.8% |
| 60 pages @300 dpi (seeds 200-209) | 100% / 100% | 100% / 100% |
| prod host, 24 pages @300 dpi | 100% / 100% | 100% / 100% |

There were no false positives on text-only letters or on forms with tables and logos. Limits:
fixtures are synthetic; circular stamp text is not read; a stamp that merges with nearby printed
text, and B/W rectangular stamps, stay as unread-ink `needs_review` regions (painted by default).

Faces: two extra passes on the image turned +/-30 deg, plus tiling at >= 1280 px for any image
above 640 px; nested duplicates from the turned passes merge into their union. The score floor stays 0.6 (0.5 added a false positive on a painting and no recall), and anything below 0.8 is flagged for review. Signature/stamp candidates must sit on bright paper (median of the non-ink pixels around them >= 160), so photos and paintings are not taken for handwriting.
`bench/faces_eval.py` (Mona Lisa variants: tilts up to 75 deg, faces 14-40 px, a squeezed
yaw-like view, low contrast): recall went from 23/26 to 25/26, with 0 false positives on 6
documents either way.

Prod host (4 CPU), A4 at 300 dpi, mean of 3 pages: OCR 3.27 s; with marks 3.88 s (+0.61 s).
Faces: 965 ms before, 1010 ms now. On the engine side, one colour PNG (1.40 s) replaces two
greyscale encodes (0.51 s each), about +0.4 s. In total that is about +1.0 s per scanned page.
