from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.detection.entities import PiiEntity


def _plugin_class():
    path = Path(__file__).parents[2] / "optional-plugins/pseudora.image_ocr/plugin.py"
    spec = importlib.util.spec_from_file_location("test_image_ocr_plugin", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.ImageOcrPlugin


def test_ocr_words_preserve_offsets_without_persisting_text():
    plugin = _plugin_class()
    words = plugin._words({
        "text": ["Mario", "Rossi", "mario@example.com"],
        "left": [1, 20, 40],
        "top": [2, 2, 2],
        "width": [15, 20, 120],
        "height": [10, 10, 10],
    })

    assert [(item["start"], item["end"]) for item in words] == [(0, 5), (6, 11), (12, 29)]
    assert words[2]["text"] == "mario@example.com"


def test_ocr_entity_spans_become_bounded_regions():
    plugin = _plugin_class()
    words = plugin._words({
        "text": ["Mario", "Rossi", "email", "mario@example.com"],
        "left": [1, 20, 1, 35],
        "top": [2, 2, 20, 20],
        "width": [15, 20, 30, 120],
        "height": [10, 10, 10, 10],
    })
    entity = PiiEntity(18, 35, "EMAIL", "mario@example.com", 1.0)

    regions = plugin._regions(words, [entity])

    assert regions == [{
        "type": "EMAIL",
        "confidence": 1.0,
        "x": 35,
        "y": 20,
        "width": 120,
        "height": 10,
    }]


@pytest.mark.asyncio
async def test_image_endpoint_fails_closed_without_plugin():
    from app.plugins.registry import PluginRegistry
    from app.routers.image import anonymize_image

    registry = PluginRegistry()
    previous = registry.all()
    registry.clear()
    try:
        with pytest.raises(HTTPException) as error:
            await anonymize_image(
                body=SimpleNamespace(image_base64="eA==", content_type="image/png"),
                context_id="test",
                context_type="generic",
                language="it",
                mode="mask",
                _api_key=SimpleNamespace(),
                tenant_id=None,
                anonymizer=SimpleNamespace(),
            )
    finally:
        registry.clear()
        for plugin in previous:
            registry.register(plugin)

    assert error.value.status_code == 503
    assert error.value.detail == "image_plugin_not_installed"
