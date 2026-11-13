"""Install/update the lightweight wheel in a private venv; user data lives elsewhere."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
    target = args.destination.absolute()
    marker = target / "orion-worker-install.json"
    environment = target / "venv"
    if target == Path(target.anchor) or any(
        path != path.resolve() for path in (target, marker, environment)
    ):
        parser.exit(1, "Worker installation needs an ordinary directory.\n")
    if args.uninstall:
        if not marker.is_file():
            parser.exit(1, "Not an Orion worker installation.\n")
        current = json.loads(marker.read_text(encoding="utf-8"))
        if not re.fullmatch(
            r"orion_worker-[\w.]+-py3-none-any\.whl", current.get("wheel", "")
        ):
            parser.exit(1, "Invalid Orion worker installation marker.\n")
        if Path(sys.prefix).resolve().is_relative_to(environment):
            parser.exit(
                1, "Run uninstall using Python outside the worker installation.\n"
            )
        if environment.exists():
            shutil.rmtree(environment)
        marker.unlink()
        if not any(target.iterdir()):
            target.rmdir()
        return
    manifest = json.loads((root / "worker-manifest.json").read_text(encoding="utf-8"))
    wheel = root / manifest["wheel"]
    if (
        not re.fullmatch(r"orion_worker-[\w.]+-py3-none-any\.whl", manifest["wheel"])
        or wheel.is_symlink()
        or hashlib.sha256(wheel.read_bytes()).hexdigest() != manifest["wheel_sha256"]
    ):
        parser.exit(1, "Worker archive integrity check failed.\n")
    lock = root / "worker.txt"
    lock_digest = manifest.get("files", {}).get(lock.name)
    if lock_digest and (
        lock.is_symlink()
        or hashlib.sha256(lock.read_bytes()).hexdigest() != lock_digest
    ):
        parser.exit(1, "Worker dependency lock integrity check failed.\n")
    if target.exists() and any(target.iterdir()) and not marker.is_file():
        parser.exit(1, "Destination contains an unrelated installation.\n")
    target.mkdir(parents=True, exist_ok=True)
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    command = [str(python), "-m", "pip"]
    version = subprocess.check_output(
        [str(python), "-c", "import sys; print(sys.version_info[:2] == (3, 12))"],
        text=True,
    )
    locked = bool(lock_digest and version.strip() == "True")
    if locked:
        subprocess.run(
            [*command, "install", "--require-hashes", "-r", str(lock)], check=True
        )
    options = ["--no-deps"] if locked else ["--upgrade"]
    subprocess.run(
        [*command, "install", *options, "--force-reinstall", str(wheel)], check=True
    )
    subprocess.run([*command, "check"], check=True)
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
