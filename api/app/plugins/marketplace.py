from __future__ import annotations

import base64
import binascii
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.plugins.installer import PluginPackageInstaller


@dataclass(frozen=True)
class MarketplaceEntry:
    name: str
    version: str
    download_url: str
    sha256: str
    signature: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "MarketplaceEntry":
        if not isinstance(payload, dict):
            raise ValueError("marketplace_entry_invalid")
        values = {key: payload.get(key) for key in ("name", "version", "download_url", "sha256")}
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise ValueError("marketplace_entry_invalid")
        signature = payload.get("signature")
        if signature is not None and not isinstance(signature, str):
            raise ValueError("marketplace_signature_invalid")
        return cls(**values, signature=signature)


class MarketplaceClient:
    """Browse and install packages from a configured, trusted marketplace origin."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        public_key: bytes | None = None,
        timeout: float = 10.0,
        max_package_bytes: int = 50_000_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._origin = self._validate_origin(base_url)
        self._token = token
        self._public_key = public_key
        self._timeout = timeout
        self._max_package_bytes = max_package_bytes
        self._transport = transport

    async def catalog(self) -> list[MarketplaceEntry]:
        payload = await self._request_json("/v1/catalog")
        entries = payload.get("plugins") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise ValueError("marketplace_catalog_invalid")
        return [MarketplaceEntry.from_payload(item) for item in entries]

    async def install(self, name: str, destination: str | Path) -> Path:
        if not name.strip():
            raise ValueError("marketplace_plugin_name_required")
        entry = next((item for item in await self.catalog() if item.name == name), None)
        if entry is None:
            raise ValueError("marketplace_plugin_not_found")
        archive = await self._download(entry.download_url)
        try:
            if self._public_key and not entry.signature:
                raise ValueError("marketplace_signature_required")
            try:
                signature = base64.b64decode(entry.signature, validate=True) if entry.signature else None
            except binascii.Error as exc:
                raise ValueError("marketplace_signature_invalid") from exc
            return PluginPackageInstaller().install(
                archive, destination, entry.sha256,
                signature=signature, public_key=self._public_key,
            )
        finally:
            archive.unlink(missing_ok=True)

    async def _request_json(self, path: str) -> object:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(self._url(path), headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def _download(self, url: str) -> Path:
        parsed = urlparse(urljoin(self._origin + "/", url))
        if parsed.scheme != "https" or parsed.netloc != urlparse(self._origin).netloc:
            raise ValueError("marketplace_download_origin_invalid")
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(parsed.geturl(), headers=self._headers())
            response.raise_for_status()
        if len(response.content) > self._max_package_bytes:
            raise ValueError("marketplace_package_too_large")
        temporary = tempfile.NamedTemporaryFile(prefix="pii-marketplace-", suffix=".zip", delete=False)
        try:
            temporary.write(response.content)
            return Path(temporary.name)
        finally:
            temporary.close()

    def _url(self, path: str) -> str:
        return urljoin(self._origin + "/", path.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    @staticmethod
    def _validate_origin(value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ValueError("marketplace_url_invalid")
        return value.rstrip("/")
