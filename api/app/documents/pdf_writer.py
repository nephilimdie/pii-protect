"""Incremental writer for image-only PDFs (one raster image per page).

Each page is serialized as soon as it is rendered, so the redacted PDF can be
streamed page by page: memory holds one encoded page plus the xref offsets,
never the whole output. The structure is the minimal PDF 1.7 subset that
needs no forward knowledge except the /Pages object number, which is reserved
up front. No metadata, text, fonts or annotations are ever written.
"""

from __future__ import annotations

from dataclasses import dataclass

_HEADER = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
_CATALOG, _PAGES = 1, 2
EOF_MARKER = b"%%EOF"


@dataclass(frozen=True)
class PageImage:
    """An already-encoded page raster: JPEG (/DCTDecode) or zlib pixels (/FlateDecode)."""

    data: bytes
    width: int
    height: int
    color_space: str  # "DeviceRGB" | "DeviceGray"
    filter: str  # "DCTDecode" | "FlateDecode"


def _num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


class ImagePdfWriter:
    """Why: a buffered pdfium output document keeps every page image in memory until
    save(); streaming needs a writer whose memory does not grow with page count.
    What: start() yields the header, add_page() yields one page's objects, finish()
    yields the page tree, catalog, xref table and trailer ending in %%EOF.
    Test: concatenate start/add_page x2/finish, open with pypdfium2, assert 2 pages,
    the given sizes and rotation, and zero text characters.
    """

    def __init__(self) -> None:
        self._offsets: list[int] = [0, 0, 0]  # index = object number; 0 is the free head
        self._position = 0
        self._kids: list[int] = []

    def _emit(self, chunk: bytes) -> bytes:
        self._position += len(chunk)
        return chunk

    def _object(self, number: int, body: bytes) -> bytes:
        self._offsets[number] = self._position
        return self._emit(b"%d 0 obj\n" % number + body + b"\nendobj\n")

    def _reserve(self) -> int:
        self._offsets.append(0)
        return len(self._offsets) - 1

    def start(self) -> bytes:
        return self._emit(_HEADER)

    def add_page(self, image: PageImage, frame: tuple[float, float], rotation: int) -> bytes:
        """`frame` is the unrotated page size in points; the image fills it exactly."""
        xobject, content, page = self._reserve(), self._reserve(), self._reserve()
        width, height = _num(frame[0]), _num(frame[1])
        draw = f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode()
        chunks = [
            self._object(xobject, (
                f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} "
                f"/ColorSpace /{image.color_space} /BitsPerComponent 8 /Filter /{image.filter} "
                f"/Length {len(image.data)} >>\nstream\n"
            ).encode() + image.data + b"\nendstream"),
            self._object(content, b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream"),
            self._object(page, (
                f"<< /Type /Page /Parent {_PAGES} 0 R /MediaBox [0 0 {width} {height}] /Rotate {rotation} "
                f"/Resources << /XObject << /Im0 {xobject} 0 R >> >> /Contents {content} 0 R >>"
            ).encode()),
        ]
        self._kids.append(page)
        return b"".join(chunks)

    def finish(self) -> bytes:
        kids = " ".join(f"{kid} 0 R" for kid in self._kids)
        chunks = [
            self._object(_PAGES, f"<< /Type /Pages /Kids [{kids}] /Count {len(self._kids)} >>".encode()),
            self._object(_CATALOG, f"<< /Type /Catalog /Pages {_PAGES} 0 R >>".encode()),
        ]
        xref_at = self._position
        table = [b"xref\n0 %d\n0000000000 65535 f \n" % len(self._offsets)]
        table.extend(b"%010d 00000 n \n" % offset for offset in self._offsets[1:])
        table.append(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n" % (len(self._offsets), _CATALOG, xref_at))
        table.append(EOF_MARKER + b"\n")
        chunks.append(self._emit(b"".join(table)))
        return b"".join(chunks)
