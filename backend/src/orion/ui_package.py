"""Build and replace Orion's packaged static UI before a server starts."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from orion.paths import PACKAGED_UI_SHELL


def build_and_package_ui(repository: Path, destination: Path, *, npm_ci: bool = False) -> None:
    ui = repository / "ui"
    if npm_ci:
        _run_npm(["npm", "ci", "--prefix", str(ui)])
    _run_npm(["npm", "run", "build", "--prefix", str(ui)])
    try:
        replace_ui_bundle(ui / "dist" / "client", destination)
    except OSError as error:
        raise RuntimeError(
            f"Orion could not package the UI at {destination}: {error}. "
            "Check write permissions and free disk space, then retry `orion web` or `./install.sh`."
        ) from error


def _run_npm(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)  # noqa: S603 - fixed npm command and checkout path.
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "Orion could not build its development UI. Install Node.js/npm and UI dependencies "
            "(`npm ci --prefix ui`), then run `orion web` again."
        ) from error


def replace_ui_bundle(source: Path, destination: Path) -> None:
    """Stage a complete bundle and swap it in, removing every old hashed asset."""
    if not (source / PACKAGED_UI_SHELL).is_file():
        raise RuntimeError(f"UI build did not create {source / PACKAGED_UI_SHELL}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{destination.name}-staged-", dir=destination.parent))
    backup: Path | None = None
    try:
        shutil.copytree(source, staged, dirs_exist_ok=True)
        if not (staged / PACKAGED_UI_SHELL).is_file():
            raise RuntimeError(f"Staged UI is missing {PACKAGED_UI_SHELL}.")
        if destination.exists() or destination.is_symlink():
            backup = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}-old-", dir=destination.parent)
            )
            backup.rmdir()
            os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except OSError:
            if backup is not None:
                os.replace(backup, destination)
                backup = None
            raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
        # If rollback itself failed, keep the old bundle at its backup path.
        if backup is not None and backup.exists() and destination.exists():
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup)
            else:
                backup.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and package Orion's static UI")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--npm-ci", action="store_true")
    arguments = parser.parse_args()
    try:
        build_and_package_ui(arguments.repository, arguments.destination, npm_ci=arguments.npm_ci)
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
