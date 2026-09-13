from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from app.plugins.manifest import PluginManifest


class PluginPackageInstaller:
    """Install a reviewed plugin archive into a local plugin directory."""

    def install(self, archive: str | Path, destination: str | Path, sha256: str) -> Path:
        archive_path = Path(archive).resolve()
        destination_path = Path(destination).resolve()
        self._verify_checksum(archive_path, sha256)
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

    def _verify_checksum(self, archive: Path, expected: str) -> None:
        if not archive.is_file() or len(expected) != 64:
            raise ValueError("plugin_archive_checksum_invalid")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expected.lower():
            raise ValueError("plugin_archive_checksum_mismatch")

    def _extract_safely(self, archive: Path, destination: Path) -> None:
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
