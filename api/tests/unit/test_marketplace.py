import hashlib
import io
import json
import zipfile

import httpx
import pytest

from app.plugins.marketplace import MarketplaceClient


def _archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("demo.plugin/plugin.json", json.dumps({
            "name": "demo.plugin",
            "version": "1.0.0",
            "entrypoint": "plugin:DemoPlugin",
        }))
        package.writestr("demo.plugin/plugin.py", "class DemoPlugin: pass")
    return stream.getvalue()


@pytest.mark.asyncio
async def test_marketplace_catalog_requires_trusted_origin_and_auth_header() -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"plugins": []})

    client = MarketplaceClient(
        "https://marketplace.example",
        token="entitlement-token",
        transport=httpx.MockTransport(handler),
    )

    assert await client.catalog() == []
    assert calls[0].headers["Authorization"] == "Bearer entitlement-token"


@pytest.mark.asyncio
async def test_marketplace_install_verifies_checksum_before_extracting(tmp_path) -> None:
    archive = _archive()
    checksum = hashlib.sha256(archive).hexdigest()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/catalog":
            return httpx.Response(200, json={"plugins": [{
                "name": "demo.plugin",
                "version": "1.0.0",
                "download_url": "/packages/demo.zip",
                "sha256": checksum,
            }]})
        return httpx.Response(200, content=archive)

    client = MarketplaceClient(
        "https://marketplace.example",
        transport=httpx.MockTransport(handler),
    )

    target = await client.install("demo.plugin", tmp_path / "plugins")

    assert target.name == "demo.plugin"
    assert (target / "plugin.json").is_file()


def test_marketplace_rejects_non_https_or_cross_origin_download() -> None:
    with pytest.raises(ValueError, match="marketplace_url_invalid"):
        MarketplaceClient("http://marketplace.example")


@pytest.mark.asyncio
async def test_marketplace_rejects_cross_origin_package_url() -> None:
    archive = _archive()
    checksum = hashlib.sha256(archive).hexdigest()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"plugins": [{
            "name": "demo.plugin",
            "version": "1.0.0",
            "download_url": "https://attacker.example/plugin.zip",
            "sha256": checksum,
        }]})

    client = MarketplaceClient("https://marketplace.example", transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="download_origin_invalid"):
        await client.install("demo.plugin", "/tmp/plugins")
