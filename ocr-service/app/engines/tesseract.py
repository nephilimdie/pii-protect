"""Tesseract 5 adapter: image in via stdin, TSV out via stdout (no files, no network)."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from app.engines import RawWord, remaining
from app.errors import ErrorCode, OcrError

logger = logging.getLogger("ocr.tesseract")


def encode_pgm(gray: Image.Image) -> bytes:
    """Why: PGM is the cheapest lossless container Leptonica reads from memory.
    What: binary P5 header + raw 8-bit rows.
    Test: a 2x1 image encodes to b"P5\\n2 1\\n255\\n" + 2 bytes.
    """
    return f"P5\n{gray.width} {gray.height}\n255\n".encode() + gray.tobytes()


def parse_tsv(tsv: str) -> list[RawWord]:
    """Why: Tesseract's TSV is the only output carrying word boxes + confidences + layout ids.
    What: keeps level-5 (word) rows with non-blank text; line ids are sequential per page in
    reading order of (block, paragraph, line).
    Test: a TSV with two words on one line yields 2 RawWords sharing ``line == 0``.
    """
    words: list[RawWord] = []
    line_ids: dict[tuple[int, int, int], int] = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        block, par, line = int(cols[2]), int(cols[3]), int(cols[4])
        left, top, width, height = (int(c) for c in cols[6:10])
        line_id = line_ids.setdefault((block, par, line), len(line_ids))
        conf = min(100.0, max(0.0, float(cols[10])))
        words.append(RawWord(text, conf, (left, top, left + width, top + height), line_id, block))
    return words


class Tesseract:
    """Why: Tesseract is the accurate engine for scans; isolating it in a subprocess keeps a
    crash or runaway page from taking the API down and makes the timeout enforceable (kill).
    What: runs ``tesseract stdin stdout`` with OMP_THREAD_LIMIT=1, LSTM-only, page segmentation 3.
    Test: ``Tesseract(cmd, tessdata).recognize(img_with_text, "eng", 300, deadline)`` returns words.
    """

    name = "tesseract"

    def __init__(self, cmd: str, tessdata_dir: Path, psm: int = 3) -> None:
        self._cmd = shutil.which(cmd) or cmd
        self._tessdata = tessdata_dir
        self._psm = psm
        self._env = {"OMP_THREAD_LIMIT": "1", "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}

    def languages(self) -> frozenset[str]:
        """Why: ``lang`` is user input; only installed models are allowed. What: model stems. Test: {"ita","eng"}."""
        if not self._tessdata.is_dir():
            return frozenset()
        return frozenset(p.stem for p in self._tessdata.glob("*.traineddata")) - {"osd"}

    def ready(self) -> dict[str, object]:
        """Why: readiness must prove the binary runs and models exist. What: version + langs. Test: keys present."""
        result = subprocess.run([self._cmd, "--version"], capture_output=True, timeout=10, env=self._env, check=False)
        version = (result.stdout or result.stderr).decode(errors="replace").splitlines()[0:1]
        return {"ok": result.returncode == 0 and bool(self.languages()), "version": version[0] if version else "",
                "languages": sorted(self.languages()), "tessdata": self._tessdata.name}

    def orientation(self, gray: Image.Image, deadline: float) -> tuple[int, float]:
        """Why: a page scanned sideways or upside down (no EXIF, no PDF /Rotate) reads as garbage.
        What: Tesseract OSD (--psm 0, osd.traineddata): degrees the page is turned counter-clockwise
        (0/90/180/270) and the orientation confidence; (0, 0.0) when OSD is unavailable or fails
        (e.g. too few characters). Test: a text page rotated 90 deg CCW with Pillow -> (90, >2).
        """
        if not (self._tessdata / "osd.traineddata").is_file():
            return 0, 0.0
        args = [self._cmd, "stdin", "stdout", "--tessdata-dir", str(self._tessdata), "-l", "osd", "--psm", "0"]
        try:
            result = subprocess.run(args, input=encode_pgm(gray), capture_output=True,
                                    timeout=remaining(deadline), env=self._env, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OcrError(504, ErrorCode.TIMEOUT, "OCR did not finish within the request deadline.") from exc
        out = result.stdout.decode("utf-8", errors="replace")
        rotate = re.search(r"^Rotate:\s*(\d+)", out, re.MULTILINE)
        conf = re.search(r"^Orientation confidence:\s*([\d.]+)", out, re.MULTILINE)
        if result.returncode != 0 or not rotate or not conf:
            return 0, 0.0
        return int(rotate.group(1)) % 360, float(conf.group(1))

    def recognize(self, gray: Image.Image, lang: str, dpi: int, deadline: float) -> list[RawWord]:
        """Why/What: see class. Raises OCR_TIMEOUT (process killed) or OCR_FAILED on non-zero exit.
        Test: a deadline already passed raises 504 without spawning a process.
        """
        args = [self._cmd, "stdin", "stdout", "--tessdata-dir", str(self._tessdata), "-l", lang,
                "--oem", "1", "--psm", str(self._psm), "--dpi", str(dpi), "-c", "tessedit_create_tsv=1"]
        try:
            result = subprocess.run(args, input=encode_pgm(gray), capture_output=True,
                                    timeout=remaining(deadline), env=self._env, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OcrError(504, ErrorCode.TIMEOUT, "OCR did not finish within the request deadline.") from exc
        if result.returncode != 0:
            logger.error("tesseract exited with status %s", result.returncode)
            raise OcrError(500, ErrorCode.OCR_FAILED, "The OCR engine failed on a page.")
        return parse_tsv(result.stdout.decode("utf-8", errors="replace"))
