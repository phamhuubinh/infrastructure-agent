"""Freeze an Orion wheel as the Windows app's owned backend process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "scripts/refactor/locks"
NAME = "OrionBackend"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(wheel: Path, output: Path) -> None:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError(
            "The Orion desktop sidecar requires a native Windows x64 build host."
        )
    if sys.version_info[:2] != (3, 12):
        raise ValueError("The desktop sidecar dependency locks require Python 3.12.")
    match = re.fullmatch(
        r"orion-(\d+\.\d+\.\d+(?:[a-z]\d+)?)-py3-none-any\.whl", wheel.name
    )
    if match is None or not wheel.is_file():
        raise ValueError("Expected a built Orion backend wheel.")
    if output.exists() or output.is_symlink() or output.is_junction():
        raise ValueError("Use a new destination for the desktop sidecar.")
    output.parent.mkdir(parents=True, exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    with tempfile.TemporaryDirectory(
        prefix=".orion-sidecar-", dir=output.parent
    ) as directory:
        stage = Path(directory)
        python = stage / "venv/Scripts/python.exe"

        def run(*command: str | Path) -> None:
            subprocess.run(command, cwd=stage, env=environment, check=True)

        run(sys.executable, "-m", "venv", stage / "venv")
        run(
            python,
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "-r",
            LOCKS / "core.txt",
            "-r",
            LOCKS / "freezer.txt",
        )
        run(python, "-m", "pip", "install", "--no-deps", wheel)
        run(python, "-m", "pip", "check")
        run(
            python,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--noupx",
            "--name",
            NAME,
            "--collect-data",
            "orion",
            "--collect-submodules",
            "uvicorn",
            "--copy-metadata",
            "mcp",
            "--copy-metadata",
            "mcp-types",
            ROOT / "scripts/desktop/sidecar_entry.py",
        )
        bundle = stage / "dist" / NAME
        manifest = {
            "version": match.group(1),
            "platform": "windows-x64",
            "entrypoint": NAME + ".exe",
            "wheel_sha256": sha256(wheel),
            "files": {
                path.relative_to(bundle).as_posix(): sha256(path)
                for path in sorted(bundle.rglob("*"))
                if path.is_file()
            },
        }
        (bundle / "sidecar-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        bundle.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.wheel.resolve(), args.output.absolute())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Orion sidecar build failed: {error}\n")


if __name__ == "__main__":
    main()
