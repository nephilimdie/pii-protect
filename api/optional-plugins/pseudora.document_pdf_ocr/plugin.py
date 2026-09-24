from __future__ import annotations

import io
from typing import Awaitable, Callable

from app.detection.entities import PiiEntity
from app.plugins.base import BasePlugin
from app.plugins.document_contract import DocumentAnonymizationResult


class PdfOcrPlugin(BasePlugin):
    """Optional PDF OCR plugin that emits a redacted image-only PDF."""

    name = "pseudora.document_pdf_ocr"
    version = "0.1.0"

    async def on_anonymize(self, text, entities):
        return entities

    async def on_deanonymize(self, text, mapping):
        return text

    async def anonymize_document(
        self,
        *,
        payload: bytes,
        content_type: str,
        detect: Callable[[str], Awaitable[list[PiiEntity]]],
        max_pixels: int,
        max_pages: int,
        **_kwargs,
    ) -> DocumentAnonymizationResult:
        if content_type != "application/pdf":
            raise ValueError("unsupported_document_type")
        pdfium, pytesseract, output_type, Image = self._dependencies()
        try:
            document = pdfium.PdfDocument(payload)
            page_count = len(document)
        except Exception as exc:
            raise ValueError("invalid_pdf") from exc
        if page_count > max_pages:
            raise ValueError("document_page_limit_exceeded")
        rendered = []
        regions = []
        for page_number in range(page_count):
            page = document[page_number]
            image = page.render(scale=2).to_pil().convert("RGB")
            if image.width * image.height > max_pixels:
                raise ValueError("document_pixel_limit_exceeded")
            data = pytesseract.image_to_data(image, output_type=output_type, lang="ita+eng")
            words = self._words(data)
            entities = await detect(" ".join(word["text"] for word in words)) if words else []
            page_regions = self._regions(words, entities, page_number)
            for region in page_regions:
                self._redact(image, region)
            rendered.append(image)
            regions.extend(page_regions)
            page.close()
        if not rendered:
            raise ValueError("empty_pdf")
        output = io.BytesIO()
        rendered[0].save(output, format="PDF", save_all=True, append_images=rendered[1:])
        return DocumentAnonymizationResult(output.getvalue(), "application/pdf", page_count, regions)

    @staticmethod
    def _dependencies():
        try:
            import pypdfium2 as pdfium
            import pytesseract
            from PIL import Image
            from pytesseract import Output
        except Exception as exc:
            raise RuntimeError("pdf_ocr_dependencies_unavailable") from exc
        return pdfium, pytesseract, Output.DICT, Image

    @staticmethod
    def _words(data: dict[str, list]) -> list[dict[str, object]]:
        words = []
        cursor = 0
        for index, value in enumerate(data.get("text", [])):
            text = str(value).strip()
            if not text:
                continue
            words.append({
                "text": text,
                "start": cursor,
                "end": cursor + len(text),
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
            })
            cursor += len(text) + 1
        return words

    @classmethod
    def _regions(cls, words: list[dict[str, object]], entities: list[PiiEntity], page: int):
        regions = []
        for entity in entities:
            selected = [word for word in words if word["start"] < entity.end and word["end"] > entity.start]
            if not selected:
                continue
            left = min(int(word["left"]) for word in selected)
            top = min(int(word["top"]) for word in selected)
            right = max(int(word["left"]) + int(word["width"]) for word in selected)
            bottom = max(int(word["top"]) + int(word["height"]) for word in selected)
            regions.append({
                "page": page,
                "type": entity.pii_type,
                "confidence": round(entity.score, 4),
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
            })
        return regions

    @staticmethod
    def _redact(image, region):
        from PIL import ImageDraw
        left = int(region["x"])
        top = int(region["y"])
        ImageDraw.Draw(image).rectangle((left, top, left + int(region["width"]), top + int(region["height"])), fill="black")
