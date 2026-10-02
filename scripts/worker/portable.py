"""Native, unobfuscated onedir worker build in a server-free isolated build venv."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def build(repository: Path, output: Path, allow_dirty: bool = False) -> Path:
    repository, output = repository.resolve(), output.resolve()
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    if not allow_dirty and subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repository
    ):
        raise ValueError("Portable build requires clean source")
    version = (
        (repository / "backend/src/orion_endpoint/__init__.py")
        .read_text()
        .split('__version__ = "')[1]
        .split('"')[0]
    )
    platform = "windows-x64" if os.name == "nt" else "linux-x86_64"
    work = output.parent / f"portable-build-{platform}"
    work.mkdir(parents=True, exist_ok=True)
    environment = work / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "pyinstaller==6.16.0",
            str(repository / "worker"),
        ],
        check=True,
    )
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
    if os.name == "nt":
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    bundle.write(
                        path, f"{root}/{path.relative_to(directory).as_posix()}"
                    )
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(directory, arcname=root)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / f"portable-{platform}.json").write_text(
        json.dumps(
            {
                "version": version,
                "source_sha": sha,
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
    ):
        raise ValueError("Portable platform build/version/source mismatch")
    manifest = {
        "version": records[0]["version"],
        "source_sha": records[0]["source_sha"],
        "artifacts": [record["artifact"] for record in records],
    }
    for artifact in manifest["artifacts"]:
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
