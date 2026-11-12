"""Build and verify the minimal, platform-specific Orion release payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[a-z][0-9]+)?$")
PLATFORMS = {"linux-x86_64": "install.sh", "windows-x64": "install.ps1"}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(root: Path) -> dict[str, str]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Missing or unsafe UI directory: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Release payload contains a symlink: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = digest(path)
        elif not path.is_dir():
            raise ValueError(f"Unsupported release payload entry: {path}")
    if "_shell.html" not in files:
        raise ValueError("Packaged UI is missing _shell.html")
    return files


def verify(root: Path, platform: str) -> dict[str, object]:
    manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    if platform not in PLATFORMS or manifest.get("platform") != platform:
        raise ValueError("Release platform mismatch")
    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Invalid release version")
    suffix = ".tar.gz" if platform == "linux-x86_64" else ".zip"
    if manifest.get("artifact") != f"orion-{version}-{platform}{suffix}":
        raise ValueError("Release artifact identity mismatch")
    commit = manifest.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    wheel = f"orion-{version}-py3-none-any.whl"
    if manifest.get("wheel") != wheel:
        raise ValueError("Wheel name/version mismatch")
    expected_ui = manifest.get("ui_files")
    if (
        not isinstance(expected_ui, dict)
        or not expected_ui
        or not all(
            isinstance(key, str)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in expected_ui.items()
        )
    ):
        raise ValueError("Invalid UI file manifest")
    expected_entries = {
        "release-manifest.json",
        "payload.py",
        PLATFORMS[platform],
        wheel,
        *{f"ui/{name}" for name in expected_ui},
    }
    core_hash = manifest.get("core_lock_sha256")
    if core_hash is not None:
        if not isinstance(core_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", core_hash
        ):
            raise ValueError("Invalid runtime dependency lock digest")
        expected_entries.add("core.txt")
    actual_entries = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual_entries != expected_entries:
        raise ValueError("Release files are missing or unexpected")
    for path in root.rglob("*"):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ValueError(f"Unsafe release entry: {path}")
    if digest(root / wheel) != manifest.get("wheel_sha256"):
        raise ValueError("Wheel SHA-256 mismatch")
    if inventory(root / "ui") != expected_ui:
        raise ValueError("Packaged UI SHA-256 mismatch")
    if core_hash is not None and digest(root / "core.txt") != core_hash:
        raise ValueError("Runtime dependency lock SHA-256 mismatch")
    return manifest


def uninstall(prefix: Path, launcher: Path | None) -> None:
    prefix = prefix.absolute()
    if prefix != prefix.resolve() or prefix == Path(prefix.anchor):
        raise ValueError("Uninstall requires an ordinary installation prefix")
    environment, frontend = prefix / ".venv", prefix / ".orion-ui"
    marker = environment / ".orion-build.json"
    for path in (environment, frontend, marker):
        if path != path.resolve():
            raise ValueError("Uninstall does not follow links or junctions")
    if not marker.is_file():
        raise ValueError("Installation marker is missing")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("version"), str)
        or not VERSION_PATTERN.fullmatch(metadata["version"])
        or not isinstance(metadata.get("source_sha"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", metadata["source_sha"])
    ):
        raise ValueError("Installation marker is invalid")
    if Path(sys.prefix).resolve().is_relative_to(environment):
        raise ValueError("Run uninstall using Python outside the Orion installation")
    for key in ("ORION_DATA_DIR", "ORION_DATABASE_PATH", "ORION_LOG_PATH"):
        if configured := os.environ.get(key):
            data = Path(configured).expanduser().resolve()
            if any(data.is_relative_to(owned) for owned in (environment, frontend)):
                raise ValueError(
                    f"Move {key} outside the install-owned directories first"
                )
    if launcher is not None:
        launcher = launcher.absolute()
        if launcher != launcher.resolve() or launcher.name not in {
            "orion",
            "orion.cmd",
        }:
            raise ValueError("Uninstall requires an ordinary Orion launcher")
        encoding = locale.getencoding() if launcher.suffix else "utf-8"
        lines = launcher.read_text(encoding=encoding).splitlines()
        executable = environment / (
            "Scripts/orion.exe" if launcher.suffix else "bin/orion"
        )
        if launcher.suffix:
            expected = f'"{str(executable).replace("%", "%%")}" %*'
            valid = (
                lines[:1] == ["@REM Orion managed launcher"] and lines[-1] == expected
            )
        else:
            valid = lines[1:2] == ["# Orion managed launcher"] and shlex.split(
                lines[-1]
            ) == ["exec", str(executable), "$@"]
        if not valid:
            raise ValueError("Launcher is not managed by this Orion installation")
    if frontend.exists():
        shutil.rmtree(frontend)
    shutil.rmtree(environment)
    if launcher is not None:
        launcher.unlink()


def _add_tar(archive: tarfile.TarFile, root: Path, name: str, path: Path) -> None:
    info = archive.gettarinfo(
        str(path), arcname=f"{name}/{path.relative_to(root).as_posix()}"
    )
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o755 if path.is_dir() or path.name == "install.sh" else 0o644
    if path.is_file():
        with path.open("rb") as stream:
            archive.addfile(info, stream)
    else:
        archive.addfile(info)


def _archive(root: Path, output: Path, platform: str) -> None:
    if platform == "linux-x86_64":
        import gzip

        with (
            output.open("wb") as stream,
            gzip.GzipFile(
                filename="", fileobj=stream, mode="wb", mtime=0
            ) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as archive,
        ):
            for path in sorted(root.rglob("*"), key=Path.as_posix):
                _add_tar(archive, root, root.name, path)
    else:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*"), key=Path.as_posix):
                if not path.is_file():
                    continue
                entry = zipfile.ZipInfo(
                    f"{root.name}/{path.relative_to(root).as_posix()}"
                )
                entry.date_time = (1980, 1, 1, 0, 0, 0)
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())


def build(
    repository: Path, wheel: Path, ui: Path, output: Path, *, allow_dirty: bool = False
) -> list[Path]:
    repository = repository.resolve()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository,
        text=True,
    )
    dirty = bool(status.strip())
    if dirty and not allow_dirty:
        raise ValueError("Release build requires a clean checkout")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    version_file = repository / "backend/src/orion/_version.py"
    match = re.search(
        r'^__version__ = "([^"]+)"$', version_file.read_text(), re.MULTILINE
    )
    if match is None or not VERSION_PATTERN.fullmatch(match.group(1)):
        raise ValueError("Invalid Orion version source")
    version = match.group(1)
    expected_wheel = f"orion-{version}-py3-none-any.whl"
    if wheel.name != expected_wheel or not wheel.is_file():
        raise ValueError(f"Expected built wheel {expected_wheel}")
    ui_files = inventory(ui)
    output.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for platform, installer in PLATFORMS.items():
        name = f"orion-{version}-{platform}"
        suffix = ".tar.gz" if platform == "linux-x86_64" else ".zip"
        artifact = output / f"{name}{suffix}"
        with tempfile.TemporaryDirectory(
            prefix=".orion-release-", dir=output
        ) as temporary:
            stage = Path(temporary)
            root = stage / name
            root.mkdir()
            shutil.copy2(wheel, root / wheel.name)
            shutil.copytree(ui, root / "ui")
            shutil.copy2(repository / "scripts/release/payload.py", root / "payload.py")
            shutil.copy2(repository / "scripts/release" / installer, root / installer)
            shutil.copy2(
                repository / "scripts/refactor/locks/core.txt", root / "core.txt"
            )
            manifest = {
                "version": version,
                "commit": commit,
                "source_dirty": dirty,
                "platform": platform,
                "artifact": artifact.name,
                "wheel": wheel.name,
                "wheel_sha256": digest(root / wheel.name),
                "core_lock_sha256": digest(root / "core.txt"),
                "ui_files": ui_files,
            }
            (root / "release-manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            verify(root, platform)
            staged_archive = stage / artifact.name
            _archive(root, staged_archive, platform)
            staged_archive.replace(artifact)
        result.append(artifact)
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in result),
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--repository", type=Path, required=True)
    builder.add_argument("--wheel", type=Path, required=True)
    builder.add_argument("--ui", type=Path, required=True)
    builder.add_argument("--output", type=Path, required=True)
    builder.add_argument(
        "--allow-dirty", action="store_true", help="Local artifact validation only."
    )
    verifier = commands.add_parser("verify")
    verifier.add_argument("--root", type=Path, required=True)
    verifier.add_argument("--platform", choices=PLATFORMS, required=True)
    remover = commands.add_parser("uninstall")
    remover.add_argument("--prefix", type=Path, required=True)
    remover.add_argument("--launcher", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            for path in build(
                args.repository,
                args.wheel,
                args.ui,
                args.output,
                allow_dirty=args.allow_dirty,
            ):
                print(path)
        elif args.command == "verify":
            verify(args.root, args.platform)
        else:
            uninstall(args.prefix, args.launcher)
    except (
        ValueError,
        OSError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Release payload error: {error}\n")


if __name__ == "__main__":
    main()
