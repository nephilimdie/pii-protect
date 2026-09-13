import hashlib
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.plugins.installer import PluginPackageInstaller


def _archive(path, root="demo.plugin"):
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(f"{root}/plugin.json", '{"name":"demo.plugin","version":"1.0","entrypoint":"plugin:Demo"}')
        package.writestr(f"{root}/plugin.py", "class Demo: pass")


def test_installer_verifies_checksum_and_extracts_plugin(tmp_path):
    archive = tmp_path / "demo.zip"
    _archive(archive)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()

    target = PluginPackageInstaller().install(archive, tmp_path / "plugins", checksum)

    assert target.name == "demo.plugin"
    assert (target / "plugin.json").is_file()


def test_installer_rejects_checksum_mismatch(tmp_path):
    archive = tmp_path / "demo.zip"
    _archive(archive)

    with pytest.raises(ValueError, match="checksum_mismatch"):
        PluginPackageInstaller().install(archive, tmp_path / "plugins", "0" * 64)


def test_installer_rejects_zip_slip(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape.txt", "no")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="path_escape"):
        PluginPackageInstaller().install(archive, tmp_path / "plugins", checksum)


def test_installer_verifies_optional_ed25519_signature(tmp_path):
    archive = tmp_path / "signed.zip"
    _archive(archive)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signature = private_key.sign(archive.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()

    target = PluginPackageInstaller().install(
        archive, tmp_path / "plugins", checksum,
        signature=signature, public_key=public_key,
    )

    assert target.is_dir()


def test_installer_rejects_invalid_signature(tmp_path):
    archive = tmp_path / "signed.zip"
    _archive(archive)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="signature_invalid"):
        PluginPackageInstaller().install(
            archive, tmp_path / "plugins", checksum,
            signature=b"invalid", public_key=public_key,
        )
