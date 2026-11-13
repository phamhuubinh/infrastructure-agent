"""Cross-platform development and release checks for Orion."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "scripts" / "refactor" / "locks"
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
UI = ROOT / "ui"
WORK = ROOT / "release-work"
CHECKED_SCRIPTS = (
    "scripts/desktop",
    "scripts/linux",
    "scripts/refactor/dev.py",
    "scripts/release",
    "scripts/windows",
    "scripts/worker",
)


def run(
    *command: str | Path, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> None:
    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        env={**(env if env is not None else os.environ), "PYTHONUTF8": "1"},
    )


def executable(name: str) -> str:
    found = shutil.which(name + ".cmd" if name == "npm" and os.name == "nt" else name)
    if not found:
        raise ValueError(f"{name} is required on PATH.")
    return found


def version(*command: str | Path) -> str:
    return subprocess.check_output(command, cwd=ROOT, encoding="utf-8").strip()


def check_python(python: Path) -> str:
    actual = version(python, "-c", "import platform; print(platform.python_version())")
    target = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    if actual.split(".")[:2] != target.split(".")[:2]:
        raise ValueError(
            f"The development lock needs Python 3.12. CI uses {target}, found {actual}."
        )
    return actual


def npm() -> str:
    node = version(executable("node"), "--version").removeprefix("v")
    target = (ROOT / ".node-version").read_text(encoding="utf-8").strip()
    if node != target:
        raise ValueError(f"Use Node {target} for the UI lock and build. Found {node}.")
    return executable("npm")


def bootstrap(python: Path, backend_only: bool) -> None:
    if not python.is_file():
        if python != PYTHON:
            raise ValueError(f"Python environment does not exist at {python}.")
        check_python(Path(sys.executable))
        run(sys.executable, "-m", "venv", VENV)
    check_python(python)
    npm_bin = None if backend_only else npm()
    run(python, "-m", "pip", "install", "--require-hashes", "-r", LOCKS / "dev.txt")
    run(
        python,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        "-e",
        "./backend[dev]",
    )
    run(python, "-m", "pip", "check")
    if npm_bin:
        run(npm_bin, "ci", cwd=UI)


def check(python: Path, backend_only: bool) -> None:
    check_python(python)
    npm_bin = None if backend_only else npm()
    for operation in (("check",), ("format", "--check")):
        run(
            python,
            "-m",
            "ruff",
            *operation,
            "backend/src",
            "backend/tests",
            *CHECKED_SCRIPTS,
        )
    run(python, "-m", "mypy", "--config-file", "backend/pyproject.toml", "backend/src")
    for script in ("openapi.py", "sdk.py", "architecture_check.py"):
        run(python, ROOT / "backend/scripts" / script)
    run(python, "-m", "pytest", "scripts/refactor/test_tools.py")
    if sys.platform == "win32":
        run(python, "scripts/windows/regression_check.py", "test")
    elif sys.platform == "linux":
        run(python, "-m", "pytest", "backend/tests")
        if npm_bin:
            run(python, "backend/scripts/operations_check.py")
    else:
        raise ValueError("Development checks support Windows and Linux.")
    if npm_bin:
        run(npm_bin, "run", "lint", cwd=UI)
        run(executable("node"), "node_modules/typescript/bin/tsc", "--noEmit", cwd=UI)
        run(npm_bin, "test", "--", "--run", cwd=UI)
        run(npm_bin, "run", "test:packaged-ui", cwd=UI)
    run("git", "diff", "--check")


def product_version(path: str) -> str:
    module = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError(f"No product version in {path}.")


def build(python: Path, backend_only: bool, *, package: bool) -> None:
    check_python(python)
    npm_bin = None if backend_only else npm()
    if package and version("git", "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Release packaging requires a clean checkout.")
    env = {
        **os.environ,
        "SOURCE_DATE_EPOCH": version("git", "show", "-s", "--format=%ct", "HEAD"),
    }
    dist = WORK / "dist"
    for source in ("backend", "worker"):
        run(
            python,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            source,
            "--outdir",
            dist,
            env=env,
        )
    if npm_bin:
        run(npm_bin, "run", "build", cwd=UI, env=env)
    if not package:
        return
    server = product_version("backend/src/orion/_version.py")
    worker = product_version("backend/src/orion_endpoint/__init__.py")
    output = WORK / "artifacts"
    run(
        python,
        "scripts/release/payload.py",
        "build",
        "--repository",
        ROOT,
        "--wheel",
        dist / f"orion-{server}-py3-none-any.whl",
        "--ui",
        UI / "dist/client",
        "--output",
        output,
    )
    run(
        python,
        "scripts/worker/payload.py",
        "--repository",
        ROOT,
        "--wheel",
        dist / f"orion_worker-{worker}-py3-none-any.whl",
        "--output",
        output,
    )


def lock() -> None:
    backend = tomllib.loads(
        (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    )
    worker = tomllib.loads((ROOT / "worker/pyproject.toml").read_text(encoding="utf-8"))
    core = backend["project"]["dependencies"]
    dev = (
        core
        + backend["project"]["optional-dependencies"]["dev"]
        + ["editables>=0.3,<1"]
    )
    worker_runtime = worker["project"]["dependencies"]
    portable = worker_runtime + worker["build-system"]["requires"]
    freezer = ["pyinstaller==6.16.0"]
    with tempfile.TemporaryDirectory(prefix="orion-lock-") as temporary:
        project = Path(temporary) / "pyproject.toml"
        for profile, dependencies in (
            ("core", core),
            ("dev", dev),
            ("worker", worker_runtime),
            ("portable", portable + freezer),
            ("freezer", freezer),
        ):
            project.write_text(
                '[project]\nname = "orion-lock-input"\nversion = "0"\n'
                'requires-python = ">=3.12,<3.13"\n'
                f"dependencies = {json.dumps(dependencies)}\n",
                encoding="utf-8",
            )
            run(
                executable("uv"),
                "pip",
                "compile",
                "--universal",
                "--python-version",
                "3.12",
                "--generate-hashes",
                "--no-header",
                "--no-annotate",
                project,
                "--output-file",
                LOCKS / f"{profile}.txt",
                "--quiet",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("doctor", "bootstrap", "check", "build", "package", "lock")
    )
    environment = parser.add_mutually_exclusive_group()
    environment.add_argument(
        "--python",
        type=Path,
        help="Existing Python 3.12 environment. Default is .venv.",
    )
    environment.add_argument(
        "--current-python",
        action="store_true",
        help="Use the interpreter invoking this command.",
    )
    parser.add_argument(
        "--backend-only", action="store_true", help="Omit the Node/npm and UI steps."
    )
    args = parser.parse_args()
    python = (
        Path(sys.executable)
        if args.current_python
        else args.python.absolute()
        if args.python
        else PYTHON
    )
    try:
        if args.command == "doctor":
            found = check_python(
                python if args.python or python.is_file() else Path(sys.executable)
            )
            print(f"Python {found}")
            print(version("git", "--version"))
            if not args.backend_only:
                print("npm " + version(npm(), "--version"))
        elif args.command == "lock":
            lock()
        elif args.command == "bootstrap":
            bootstrap(python, args.backend_only)
        elif args.command == "check":
            check(python, args.backend_only)
        else:
            if args.command == "package" and args.backend_only:
                parser.error("Packaging requires the static UI bundle.")
            build(python, args.backend_only, package=args.command == "package")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Orion {args.command} failed: {error}\n")


if __name__ == "__main__":
    main()
