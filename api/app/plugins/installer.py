from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from app.plugins.manifest import PluginManifest


class PluginPackageInstaller:
    """Install a reviewed plugin archive into a local plugin directory."""

    def install(
        self, archive: str | Path, destination: str | Path, sha256: str,
        *, signature: bytes | None = None, public_key: bytes | None = None,
    ) -> Path:
        archive_path = Path(archive).resolve()
        destination_path = Path(destination).resolve()
        self._verify_checksum(archive_path, sha256)
        if signature is not None or public_key is not None:
            if signature is None or public_key is None:
                raise ValueError("plugin_signature_arguments_incomplete")
            self._verify_signature(archive_path, signature, public_key)
        with tempfile.TemporaryDirectory(prefix="pii-plugin-") as temporary:
            extraction = Path(temporary)
            self._extract_safely(archive_path, extraction)
            manifests = list(extraction.glob("*/plugin.json"))
            if len(manifests) != 1:
                raise ValueError("plugin_archive_manifest_count_invalid")
            manifest = PluginManifest.from_file(manifests[0])
            source = manifests[0].parent
            target = destination_path / manifest.name
            if target.exists():
                raise FileExistsError(f"plugin_already_installed:{manifest.name}")
            destination_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        return target

    def _verify_signature(self, archive: Path, signature: bytes, public_key: bytes) -> None:
        try:
            key = serialization.load_pem_public_key(public_key)
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("plugin_public_key_type_invalid")
            key.verify(signature, archive.read_bytes())
        except (InvalidSignature, ValueError, TypeError) as exc:
            if isinstance(exc, ValueError) and str(exc) == "plugin_public_key_type_invalid":
                raise
            raise ValueError("plugin_signature_invalid") from exc

    def _verify_checksum(self, archive: Path, expected: str) -> None:
        if not archive.is_file() or len(expected) != 64:
            raise ValueError("plugin_archive_checksum_invalid")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expected.lower():
            raise ValueError("plugin_archive_checksum_mismatch")

    def _extract_safely(self, archive: Path, destination: Path) -> None:
        destination = destination.resolve()
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                member_path = (destination / member.filename).resolve()
                if destination not in member_path.parents and member_path != destination:
                    raise ValueError("plugin_archive_path_escape")
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, member_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
