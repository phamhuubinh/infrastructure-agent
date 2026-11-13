"""Platform worker archives contain one wheel, policy and installer; never server/UI."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _archive(root: Path, artifact: Path, *, linux: bool) -> None:
    files = sorted(root.iterdir(), key=lambda path: path.name)
    if linux:
        with (
            artifact.open("wb") as stream,
            gzip.GzipFile(
                filename="", fileobj=stream, mode="wb", mtime=0
            ) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as archive,
        ):
            for file in files:
                info = archive.gettarinfo(str(file), arcname=f"{root.name}/{file.name}")
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with file.open("rb") as source:
                    archive.addfile(info, source)
    else:
        with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.writestr(
                    zipfile.ZipInfo(f"{root.name}/{file.name}"),
                    file.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                )


def build(
    repository: Path, wheel: Path, output: Path, *, allow_dirty: bool = False
) -> list[Path]:
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repository
        ).strip()
    )
    if dirty and not allow_dirty:
        raise ValueError("Worker release requires clean source")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    import ast

    version = ast.literal_eval(
        (repository / "backend/src/orion_endpoint/__init__.py")
        .read_text()
        .split("__version__ = ")[1]
        .splitlines()[0]
    )
    if wheel.name != f"orion_worker-{version}-py3-none-any.whl":
        raise ValueError("Worker wheel/version mismatch")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for platform in ("linux-x86_64", "windows-x64"):
        name = f"orion-worker-{version}-{platform}"
        linux = platform.startswith("linux")
        artifact = output / (name + (".tar.gz" if linux else ".zip"))
        with tempfile.TemporaryDirectory(
            prefix=".orion-worker-", dir=output
        ) as temporary:
            stage = Path(temporary)
            root = stage / name
            root.mkdir()
            shutil.copy2(wheel, root / wheel.name)
            shutil.copy2(repository / "scripts/worker/install.py", root / "install.py")
            shutil.copy2(
                repository / "scripts/refactor/locks/worker.txt", root / "worker.txt"
            )
            shutil.copy2(
                repository / "worker/policy.example.json", root / "policy.example.json"
            )
            files = {file.name: digest(file) for file in root.iterdir()}
            manifest = {
                "version": version,
                "commit": commit,
                "source_dirty": dirty,
                "platform": platform,
                "wheel": wheel.name,
                "wheel_sha256": files[wheel.name],
                "files": files,
            }
            (root / "worker-manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            staged_archive = stage / artifact.name
            _archive(root, staged_archive, linux=linux)
            staged_archive.replace(artifact)
        artifacts.append(artifact)
    sums = output / "SHA256SUMS"
    previous = sums.read_text(encoding="utf-8").splitlines() if sums.exists() else []
    retained = [line for line in previous if "  orion-worker-" not in line]
    sums.write_text(
        "".join(line + "\n" for line in retained)
        + "".join(f"{digest(file)}  {file.name}\n" for file in artifacts),
        encoding="utf-8",
    )
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-dirty", action="store_true", help="Local precommit validation only"
    )
    args = parser.parse_args()
    for artifact in build(
        args.repository.resolve(), args.wheel, args.output, allow_dirty=args.allow_dirty
    ):
        print(artifact)


if __name__ == "__main__":
    main()
