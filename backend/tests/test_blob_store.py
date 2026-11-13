"""Blob bytes remain private and filesystem aliases cannot redirect operations."""

from __future__ import annotations

import os
import uuid

import pytest

from orion.knowledge.blob_store import LocalBlobStore


def test_blob_roundtrip_and_invalid_identity(tmp_path):
    blobs = LocalBlobStore(tmp_path / "blobs")
    identity = blobs.put(b"\x00private\xff")
    assert blobs.get(identity) == b"\x00private\xff"
    for value in ("../outside", identity.upper(), "", None):
        with pytest.raises(ValueError):
            blobs.get(value)
    blobs.delete(identity)
    blobs.delete(identity)
    with pytest.raises(ValueError, match="unavailable"):
        blobs.get(identity)
    if os.name != "nt":
        assert (tmp_path / "blobs").stat().st_mode & 0o077 == 0


def test_blob_hardlink_is_not_read_changed_or_deleted(tmp_path):
    blobs = LocalBlobStore(tmp_path / "blobs")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    identity = str(uuid.uuid4())
    linked = tmp_path / "blobs" / identity
    os.link(outside, linked)
    for operation in (blobs.get, blobs.delete):
        with pytest.raises(OSError):
            operation(identity)
    assert outside.read_bytes() == linked.read_bytes() == b"outside"


def test_replaced_blob_directory_is_rejected(tmp_path):
    root = tmp_path / "blobs"
    blobs = LocalBlobStore(root)
    identity = blobs.put(b"original")
    root.rename(tmp_path / "old")
    root.mkdir()
    (root / identity).write_bytes(b"replacement")
    with pytest.raises(OSError, match="directory changed"):
        blobs.get(identity)
    with pytest.raises(OSError):
        blobs.put(b"new")


def test_blob_symlink_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "blobs"
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS account cannot create symlinks; junction tested separately on Windows")
    with pytest.raises(OSError):
        LocalBlobStore(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction")
def test_blob_windows_junction_rejected(tmp_path):
    import subprocess

    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "blobs"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root), str(outside)], check=True, capture_output=True
    )
    with pytest.raises(OSError):
        LocalBlobStore(root)


def test_blob_legacy_file_permissions_upgraded(tmp_path):
    root = tmp_path / "blobs"
    root.mkdir()
    identity = str(uuid.uuid4())
    path = root / identity
    path.write_bytes(b"legacy")
    blobs = LocalBlobStore(root)
    if os.name == "nt":
        from test_document_migration import _windows_acl_text

        for item in (root, path):
            acl = _windows_acl_text(item)
            assert "D:P" in acl and acl.count("(A;") == 2 and ";;;SY)" in acl
    else:
        assert path.stat().st_mode & 0o077 == 0
    assert blobs.get(identity) == b"legacy"


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL")
def test_private_windows_acl_rejects_an_extra_grant(tmp_path):
    import subprocess

    from orion.persistence.private_files import _windows_private_acl

    path = tmp_path / "private"
    path.write_bytes(b"")
    _windows_private_acl(path, directory=False)
    _windows_private_acl(path, directory=False, validate_only=True)
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-1-0:R"],
        check=True,
        capture_output=True,
    )
    with pytest.raises(OSError, match="ACL is not private"):
        _windows_private_acl(path, directory=False, validate_only=True)
