"""Assemble the Windows desktop executable and its exact backend resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import struct
import subprocess
import tempfile
import tomllib
import zipfile
from pathlib import Path

from build_sidecar import ROOT, sha256


def require_x64_pe(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) == 64 and header.startswith(b"MZ"):
            stream.seek(struct.unpack_from("<I", header, 60)[0])
            if stream.read(6) == b"PE\x00\x00\x64\x86":
                return
    raise ValueError(f"Expected an x64 Windows PE file: {path.name}")


def write_file(bundle: zipfile.ZipFile, path: Path, name: str) -> str:
    entry = zipfile.ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = (stat.S_IFREG | 0o644) << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    digest = hashlib.sha256()
    with path.open("rb") as source, bundle.open(entry, "w", force_zip64=True) as target:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            target.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def package(
    executable: Path, sidecar: Path, output: Path, *, allow_dirty: bool
) -> Path:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    source_sha = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    if dirty and not allow_dirty:
        raise ValueError("Desktop packaging requires a clean checkout")
    if sidecar.is_symlink() or sidecar.is_junction() or not sidecar.is_dir():
        raise ValueError("Expected the managed backend resource directory")
    if output.resolve().is_relative_to(sidecar.resolve()):
        raise ValueError("Desktop archive output must be outside the backend resources")
    with (ROOT / "ui/src-tauri/Cargo.toml").open("rb") as stream:
        version = tomllib.load(stream)["package"]["version"]
    if not isinstance(version, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", version
    ):
        raise ValueError("Invalid desktop version")
    metadata_path = sidecar / "sidecar-manifest.json"
    if metadata_path.is_symlink():
        raise ValueError("Invalid desktop backend manifest path")
    metadata = json.loads(metadata_path.read_bytes())
    if (
        not isinstance(metadata, dict)
        or metadata.get("version") != version
        or metadata.get("platform") != "windows-x64"
        or metadata.get("entrypoint") != "OrionBackend.exe"
        or not isinstance(metadata.get("wheel_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", metadata["wheel_sha256"])
        or not isinstance(metadata.get("files"), dict)
    ):
        raise ValueError("Desktop backend version, platform or manifest mismatch")
    loader = executable.with_name("WebView2Loader.dll")
    require_x64_pe(executable)
    require_x64_pe(loader)
    require_x64_pe(sidecar / "OrionBackend.exe")

    root = f"OrionDesktop-{version}-windows-x64"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".orion-desktop-", dir=output) as directory:
        temporary = Path(directory)
        archive = temporary / f"{root}.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            desktop_sha = write_file(bundle, executable, f"{root}/Orion.exe")
            loader_sha = write_file(bundle, loader, f"{root}/{loader.name}")
            backend = {}
            for path in sorted(sidecar.rglob("*"), key=Path.as_posix):
                if path.is_symlink() or path.is_junction():
                    raise ValueError("Managed backend contains a linked resource")
                if path.is_file():
                    name = path.relative_to(sidecar).as_posix()
                    backend[name] = write_file(bundle, path, f"{root}/backend/{name}")
            metadata_sha = backend.pop(metadata_path.name, None)
            if backend != metadata["files"] or metadata_sha != sha256(metadata_path):
                raise ValueError("Managed backend resources differ from their manifest")
            bundle.writestr(
                zipfile.ZipInfo(f"{root}/desktop-manifest.json"),
                json.dumps(
                    {
                        "version": version,
                        "platform": "windows-x64",
                        "source_sha": source_sha,
                        "source_dirty": dirty,
                        "entrypoint": "Orion.exe",
                        "desktop_sha256": desktop_sha,
                        "webview2_loader_sha256": loader_sha,
                        "backend_manifest_sha256": metadata_sha,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        checksum = temporary / f"{archive.name}.sha256"
        checksum.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="ascii")
        artifact = archive.replace(output / archive.name)
        checksum.replace(output / checksum.name)
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    try:
        print(
            package(
                args.executable, args.sidecar, args.output, allow_dirty=args.allow_dirty
            )
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Orion desktop packaging failed: {error}\n")


if __name__ == "__main__":
    main()
