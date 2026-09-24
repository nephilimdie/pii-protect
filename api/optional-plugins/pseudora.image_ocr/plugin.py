from __future__ import annotations

import io
from typing import Awaitable, Callable

from app.detection.entities import PiiEntity
from app.plugins.base import BasePlugin
from app.plugins.image_contract import ImageAnonymizationResult


class ImageOcrPlugin(BasePlugin):
    """Optional OCR redaction plugin for PNG and JPEG images."""

    name = "pseudora.image_ocr"
    version = "0.1.0"

    async def on_anonymize(self, text, entities):
        return entities

    async def on_deanonymize(self, text, mapping):
        return text

    async def anonymize_image(
        self,
        *,
        payload: bytes,
        content_type: str,
        detect: Callable[[str], Awaitable[list[PiiEntity]]],
        max_pixels: int,
        **_kwargs,
    ) -> ImageAnonymizationResult:
        image, pytesseract, output_type = self._load_dependencies(payload, max_pixels)
        data = pytesseract.image_to_data(image, output_type=output_type, lang="ita+eng")
        words = self._words(data)
        if not words:
            return self._encode(image, content_type, [])

        entities = await detect(" ".join(item["text"] for item in words))
        regions = self._regions(words, entities)
        for region in regions:
            image = self._redact(image, region)
        return self._encode(image, content_type, regions)

    @staticmethod
    def _load_dependencies(payload: bytes, max_pixels: int):
        try:
            from PIL import Image
            import pytesseract
            from pytesseract import Output
            image = Image.open(io.BytesIO(payload)).convert("RGB")
        except Exception as exc:
            raise RuntimeError("image_ocr_dependencies_unavailable") from exc
        if image.width * image.height > max_pixels:
            raise ValueError("image_pixel_limit_exceeded")
        return image, pytesseract, Output.DICT

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
    def _regions(cls, words: list[dict[str, object]], entities: list[PiiEntity]) -> list[dict[str, object]]:
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
                "type": entity.pii_type,
                "confidence": round(entity.score, 4),
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
            })
        return regions

    @staticmethod
    def _redact(image, region: dict[str, object]):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        left = int(region["x"])
        top = int(region["y"])
        right = left + int(region["width"])
        bottom = top + int(region["height"])
        draw.rectangle((left, top, right, bottom), fill="black")
        return image

    @staticmethod
    def _encode(image, content_type: str, regions: list[dict[str, object]]) -> ImageAnonymizationResult:
        output = io.BytesIO()
        image.save(output, format="JPEG" if content_type == "image/jpeg" else "PNG")
        return ImageAnonymizationResult(output.getvalue(), content_type, regions)
