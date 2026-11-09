#!/bin/sh
# Why: OCR models must be baked into the image (the container has no egress) and be
# byte-identical between CI, local runs and prod. Every artefact is pinned by sha256.
# What: downloads tessdata_fast + tessdata_best (ita, eng; tag 4.1.0, Apache-2.0) into
# $1/tessdata/{fast,best} (plus osd, page orientation detection) and extracts the PP-OCRv4 mobile det/rec ONNX models
# (Apache-2.0) from the pinned rapidocr_onnxruntime wheel into $1/rapidocr, and the YuNet face
# detector (OpenCV Zoo face_detection_yunet_2023mar, MIT, pinned commit) into $1/yunet.
# Test: `sh scripts/fetch_models.sh /tmp/ocr-models` then `ls /tmp/ocr-models/*/*`; a
# tampered file makes `sha256sum -c` fail and the script exit non-zero.
set -eu
# Direct content hosts (github.com/<repo>/raw/ redirects answered 504 on 2026-11-09); bytes are sha256-pinned.
DEST=${1:?usage: fetch_models.sh DEST_DIR}
TESSDATA_TAG=4.1.0
WHEEL_URL=https://files.pythonhosted.org/packages/ba/12/1e5497183bdbe782dbb91bad1d0d2297dba4d2831b2652657f7517bfc6df/rapidocr_onnxruntime-1.4.4-py3-none-any.whl
WHEEL_SHA=971d7d5f223a7a808662229df1ef69893809d8457d834e6373d3854bc1782cbf
YUNET_URL=https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
YUNET_SHA=8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4

sha_check() { # sha256 path
  if command -v sha256sum >/dev/null 2>&1; then echo "$1  $2" | sha256sum -c -; else echo "$1  $2" | shasum -a 256 -c -; fi
}

fetch() { # url sha dest
  curl -fsSL --retry 3 -o "$3" "$1"
  sha_check "$2" "$3"
}

mkdir -p "$DEST/tessdata/fast" "$DEST/tessdata/best" "$DEST/rapidocr" "$DEST/yunet"
fetch "$YUNET_URL" "$YUNET_SHA" "$DEST/yunet/face_detection_yunet_2023mar.onnx"
while read -r variant lang sha; do
  fetch "https://raw.githubusercontent.com/tesseract-ocr/tessdata_${variant}/${TESSDATA_TAG}/${lang}.traineddata" "$sha" \
    "$DEST/tessdata/$variant/$lang.traineddata"
done <<LIST
fast ita b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827
fast eng 7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2
best ita 8df9c89176fb93f56bf4b2d4ede04c01c1f31d4b7697fbd76cc336df700f3f38
best eng 8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba
fast osd 9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff
best osd 9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff
LIST

WHEEL="$DEST/rapidocr/rapidocr.whl"
fetch "$WHEEL_URL" "$WHEEL_SHA" "$WHEEL"
python3 - "$WHEEL" "$DEST/rapidocr" <<'PY'
import sys, zipfile, pathlib
wheel, dest = sys.argv[1], pathlib.Path(sys.argv[2])
names = {"ch_PP-OCRv4_det_infer.onnx": "det.onnx", "ch_PP-OCRv4_rec_infer.onnx": "rec.onnx"}
with zipfile.ZipFile(wheel) as archive:
    for member in archive.namelist():
        base = member.rsplit("/", 1)[-1]
        if base in names:
            (dest / names[base]).write_bytes(archive.read(member))
missing = [n for n in names.values() if not (dest / n).exists()]
sys.exit(f"missing models: {missing}" if missing else 0)
PY
rm -f "$WHEEL"
