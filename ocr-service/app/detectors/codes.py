"""QR codes and barcodes located with zxing-cpp (Apache-2.0). Positions only: the decoded
content is never read into the response, logged or stored (it stays inside zxing's result
objects, which are dropped at once)."""
from __future__ import annotations

import zxingcpp
from PIL import Image

from app.detectors import Hit, grow

_QR = {getattr(zxingcpp.BarcodeFormat, n) for n in ("QRCode", "MicroQRCode", "RMQRCode", "QRCodeModel1", "QRCodeModel2")
       if hasattr(zxingcpp.BarcodeFormat, n)}
_QUIET = 0.1  # quiet zone + module bleed, of the code size on each side


class Codes:
    """Why: QR codes and barcodes on tickets, invoices, ID cards and boarding passes encode
    names, document numbers and booking references; they are ALWAYS redacted.
    What: ``detect(image)`` -> QR_CODE / BARCODE Hits (envelope of the 4 corners, grown by the
    quiet zone). Symbols zxing locates but cannot decode (damaged, partly hidden) are returned
    too, flagged ``needs_review``. Test: a segno QR pasted at (100, 100) yields one QR_CODE
    box containing (100, 100, 100 + side, 100 + side).
    """

    def ready(self) -> dict[str, object]:
        """Why/What: readiness entry. Test: ok is True."""
        return {"ok": True, "library": f"zxing-cpp {getattr(zxingcpp, '__version__', '')}".strip()}

    def detect(self, image: Image.Image) -> list[Hit]:
        """Why/What: see class. Test: a blank image returns []."""
        gray = image.convert("L")
        hits: list[Hit] = []
        for symbol in zxingcpp.read_barcodes(gray, try_rotate=True, try_downscale=True, try_invert=True,
                                             return_errors=True):
            p = symbol.position
            xs = [p.top_left.x, p.top_right.x, p.bottom_left.x, p.bottom_right.x]
            ys = [p.top_left.y, p.top_right.y, p.bottom_left.y, p.bottom_right.y]
            box = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
            if box[2] - box[0] < 2 and box[3] - box[1] < 2:
                continue
            linear = box[3] - box[1] < 4  # linear codes are reported as a scan line: cover the bars
            if linear:
                half = max(8.0, (box[2] - box[0]) * 0.25)
                box = (box[0], box[1] - half, box[2], box[3] + half)
            valid = bool(symbol.valid)
            hits.append(Hit("QR_CODE" if symbol.format in _QR else "BARCODE", grow(box, _QUIET, _QUIET, *gray.size),
                            1.0 if valid else 0.5, not valid or linear))
        return hits
