"""Native, unobfuscated onedir worker build in a server-free isolated build venv."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform as host_platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


def _archive(directory: Path, archive: Path, root: str, *, windows: bool) -> None:
    if windows:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*"), key=Path.as_posix):
                if path.is_file():
                    entry = zipfile.ZipInfo(
                        f"{root}/{path.relative_to(directory).as_posix()}"
                    )
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFREG | 0o644) << 16
                    bundle.writestr(
                        entry, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED
                    )
        return

    def normalized(entry: tarfile.TarInfo) -> tarfile.TarInfo:
        entry.mtime = entry.uid = entry.gid = 0
        entry.uname = entry.gname = ""
        return entry

    with (
        archive.open("wb") as stream,
        gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as bundle,
    ):
        bundle.add(directory, arcname=root, filter=normalized)


def build(repository: Path, output: Path, allow_dirty: bool = False) -> Path:
    repository, output = repository.resolve(), output.resolve()
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repository
        ).strip()
    )
    if dirty and not allow_dirty:
        raise ValueError("Portable build requires clean source")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Portable build requires Python 3.12 for its dependency lock")
    if sys.platform not in {
        "win32",
        "linux",
    } or host_platform.machine().lower() not in {
        "amd64",
        "x86_64",
    }:
        raise ValueError("Portable builds require a native Windows or Linux x64 runner")
    version = (
        (repository / "backend/src/orion_endpoint/__init__.py")
        .read_text()
        .split('__version__ = "')[1]
        .split('"')[0]
    )
    platform = "windows-x64" if os.name == "nt" else "linux-x86_64"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"portable-{platform}-", dir=output.parent
    ) as temporary:
        return _build(
            repository, output, Path(temporary), platform, version, sha, dirty
        )


def _build(
    repository: Path,
    output: Path,
    work: Path,
    platform: str,
    version: str,
    sha: str,
    dirty: bool,
) -> Path:
    environment = work / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "-r",
            str(repository / "scripts/refactor/locks/portable.txt"),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            str(repository / "worker"),
        ],
        check=True,
    )
    subprocess.run([str(python), "-m", "pip", "check"], check=True)
    name = "OrionRemote" if os.name == "nt" else "orion-remote"
    backend = "win32" if os.name == "nt" else "xorg"
    subprocess.run(
        [
            str(python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--noupx",
            "--name",
            name,
            "--distpath",
            str(work / "dist"),
            "--workpath",
            str(work / "work"),
            "--specpath",
            str(work),
            "--collect-all",
            "playwright",
            "--collect-all",
            "pynput",
            "--hidden-import",
            f"pynput.keyboard._{backend}",
            "--hidden-import",
            f"pynput.mouse._{backend}",
            str(repository / "scripts/worker/portable_entry.py"),
        ],
        cwd=work,
        check=True,
    )
    directory = work / "dist" / name
    shutil.copy2(
        repository / "worker/policy.example.json", directory / "policy.example.json"
    )
    files = {
        str(path.relative_to(directory)).replace(os.sep, "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    (directory / "portable-manifest.json").write_text(
        json.dumps(
            {
                "version": version,
                "source_sha": sha,
                "source_dirty": dirty,
                "platform": platform,
                "files": files,
                "entrypoint": name + (".exe" if os.name == "nt" else ""),
                "format": "pyinstaller-onedir",
                "python_prerequisite": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output.mkdir(parents=True, exist_ok=True)
    root = f"OrionRemote-{version}-{platform}"
    archive = output / (root + (".zip" if os.name == "nt" else ".tar.gz"))
    _archive(directory, archive, root, windows=os.name == "nt")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / f"portable-{platform}.json").write_text(
        json.dumps(
            {
                "version": version,
                "source_sha": sha,
                "source_dirty": dirty,
                "artifact": {
                    "filename": archive.name,
                    "platform": platform,
                    "sha256": digest,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return archive


def combine(output: Path) -> None:
    records = [
        json.loads(path.read_text()) for path in sorted(output.glob("portable-*.json"))
    ]
    if (
        len(records) != 2
        or len({(r["version"], r["source_sha"]) for r in records}) != 1
        or any(r.get("source_dirty") is not False for r in records)
        or {r["artifact"]["platform"] for r in records}
        != {"windows-x64", "linux-x86_64"}
        or not re.fullmatch(r"[0-9a-f]{40}", records[0]["source_sha"])
        or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-z][0-9]+)?", records[0]["version"]
        )
    ):
        raise ValueError("Portable platform build/version/source mismatch")
    manifest = {
        "version": records[0]["version"],
        "source_sha": records[0]["source_sha"],
        "artifacts": [record["artifact"] for record in records],
    }
    for artifact in manifest["artifacts"]:
        platform = artifact["platform"]
        suffix = ".zip" if platform == "windows-x64" else ".tar.gz"
        expected = f"OrionRemote-{manifest['version']}-{platform}{suffix}"
        if artifact["filename"] != expected:
            raise ValueError("Portable archive filename mismatch")
        if (
            hashlib.sha256((output / artifact["filename"]).read_bytes()).hexdigest()
            != artifact["sha256"]
        ):
            raise ValueError("Portable checksum mismatch")
    (output / "worker-artifacts.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sums = output / "SHA256SUMS"
    previous = sums.read_text() if sums.exists() else ""
    previous = "\n".join(
        line for line in previous.splitlines() if "OrionRemote-" not in line
    )
    sums.write_text(
        previous
        + ("\n" if previous else "")
        + "".join(f"{a['sha256']}  {a['filename']}\n" for a in manifest["artifacts"])
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--combine", action="store_true")
    args = parser.parse_args()
    if args.combine:
        combine(args.output)
    else:
        print(build(args.repository, args.output, args.allow_dirty))
