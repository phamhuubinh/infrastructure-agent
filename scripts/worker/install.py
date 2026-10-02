"""Install/update the lightweight wheel in a private venv; user data lives elsewhere."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    target = args.destination.resolve()
    marker = target / "orion-worker-install.json"
    if args.uninstall:
        if not marker.is_file():
            parser.exit(1, "Not an Orion worker installation.\n")
        shutil.rmtree(target)
        return
    manifest = json.loads((root / "worker-manifest.json").read_text(encoding="utf-8"))
    wheel = root / manifest["wheel"]
    if (
        wheel.name != manifest["wheel"]
        or hashlib.sha256(wheel.read_bytes()).hexdigest() != manifest["wheel_sha256"]
    ):
        parser.exit(1, "Worker archive integrity check failed.\n")
    if target.exists() and any(target.iterdir()) and not marker.is_file():
        parser.exit(1, "Destination contains an unrelated installation.\n")
    target.mkdir(parents=True, exist_ok=True)
    environment = target / "venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            str(wheel),
        ],
        check=True,
    )
    marker.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    print(
        environment
        / (
            "Scripts/orion-worker.exe"
            if sys.platform == "win32"
            else "bin/orion-worker"
        )
    )


if __name__ == "__main__":
    main()
