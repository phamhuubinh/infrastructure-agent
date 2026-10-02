"""Release archive composition and integrity contracts."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_payload", REPOSITORY / "scripts/release/payload.py"
)
assert SPEC is not None and SPEC.loader is not None
payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(payload)


def test_release_archives_manifest_and_tamper_rejection(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    version = __import__("orion._version", fromlist=["__version__"]).__version__
    wheel = tmp_path / f"orion-{version}-py3-none-any.whl"
    wheel.write_bytes(b"wheel fixture")
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "_shell.html").write_text("<html>fixture</html>")
    (ui / "assets").mkdir()
    (ui / "assets/app.js").write_text("fixture")
    original = payload.subprocess.check_output

    def git_output(command, **kwargs):  # type: ignore[no-untyped-def]
        if command[1] == "status":
            return ""
        if command[1] == "rev-parse":
            return "a" * 40 + "\n"
        return original(command, **kwargs)

    monkeypatch.setattr(payload.subprocess, "check_output", git_output)
    output = tmp_path / "artifacts"
    linux, windows = payload.build(REPOSITORY, wheel, ui, output)
    assert linux.name == f"orion-{version}-linux-x86_64.tar.gz"
    assert windows.name == f"orion-{version}-windows-x64.zip"
    assert linux.is_file() and windows.is_file()
    assert len((output / "SHA256SUMS").read_text().splitlines()) == 2
    for platform, archive in (("linux-x86_64", linux), ("windows-x64", windows)):
        root = output / f"orion-{version}-{platform}"
        manifest = payload.verify(root, platform)
        assert manifest["version"] == version
        assert manifest["artifact"] == archive.name
        assert manifest["commit"] == "a" * 40
        assert manifest["wheel_sha256"] == payload.digest(root / wheel.name)
        assert manifest["ui_files"] == payload.inventory(root / "ui")
        if platform == "linux-x86_64":
            with tarfile.open(archive) as package:
                names = package.getnames()
        else:
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
        assert any(name.endswith("/release-manifest.json") for name in names)
        assert any(name.endswith("/ui/_shell.html") for name in names)
        assert not any(
            "backend/" in name or "node_modules" in name or ".env" in name for name in names
        )
        installer = (root / payload.PLATFORMS[platform]).read_text()
        assert "npm" not in installer and "node" not in installer
        pip_install = "pip install" if platform == "linux-x86_64" else "'pip', 'install'"
        assert installer.index("verify") < installer.index(pip_install)

        wheel_path = root / wheel.name
        wheel_path.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="Wheel SHA-256 mismatch"):
            payload.verify(root, platform)
        wheel_path.write_bytes(b"wheel fixture")
        shell = root / "ui/_shell.html"
        shell.write_text("tampered")
        with pytest.raises(ValueError, match="Packaged UI SHA-256 mismatch"):
            payload.verify(root, platform)
        shell.write_text("<html>fixture</html>")
        (root / "ui/extra.js").write_text("extra")
        with pytest.raises(ValueError, match="missing or unexpected"):
            payload.verify(root, platform)


def test_dirty_checkout_rejected(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(payload.subprocess, "check_output", lambda *args, **kwargs: " M file\n")
    with pytest.raises(ValueError, match="clean checkout"):
        payload.build(REPOSITORY, tmp_path / "missing.whl", tmp_path / "ui", tmp_path / "output")


def test_linux_release_installer_orders_model_and_launcher(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    wheel = root / "orion-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"fixture")
    (root / "ui").mkdir()
    (root / "ui/_shell.html").write_text("fixture")
    (root / "payload.py").write_bytes((REPOSITORY / "scripts/release/payload.py").read_bytes())
    (root / "install.sh").write_bytes((REPOSITORY / "scripts/release/install.sh").read_bytes())
    (root / "release-manifest.json").write_text(
        __import__("json").dumps(
            {
                "version": "0.1.0",
                "commit": "a" * 40,
                "platform": "linux-x86_64",
                "artifact": "orion-0.1.0-linux-x86_64.tar.gz",
                "wheel": wheel.name,
                "wheel_sha256": payload.digest(wheel),
                "ui_files": payload.inventory(root / "ui"),
            }
        )
    )
    prefix = tmp_path / "install with spaces"
    scripts = prefix / ".venv/bin"
    scripts.mkdir(parents=True)
    fake_python = scripts / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-c" && "$2" == *"sys.version_info"* ]]; then exit 0; fi\n'
        'printf "python:%s\n" "$*" >> "$ORION_RELEASE_TRACE"\n'
    )
    fake_python.chmod(0o755)
    fake_orion = scripts / "orion"
    fake_orion.write_text(
        "#!/usr/bin/env bash\n"
        'printf "orion:%s\n" "$*" >> "$ORION_RELEASE_TRACE"\n'
        'exit "$ORION_MODEL_EXIT"\n'
    )
    fake_orion.chmod(0o755)
    trace = tmp_path / "trace"
    environment = {
        **os.environ,
        "ORION_PYTHON": sys.executable,
        "HOME": str(tmp_path),
        "XDG_BIN_HOME": str(tmp_path / "bin"),
        "ORION_RELEASE_TRACE": str(trace),
        "ORION_MODEL_EXIT": "23",
    }
    command = ["bash", str(root / "install.sh"), "--prefix", str(prefix), "--global-launcher"]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert first.returncode == 23 and "Installed Orion" not in first.stdout
    assert not (tmp_path / "bin/orion").exists()
    assert trace.read_text().splitlines()[-1] == "orion:model install embeddings"

    environment["ORION_MODEL_EXIT"] = "0"
    second = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert second.returncode == 0 and "Installed Orion" in second.stdout
    launcher = tmp_path / "bin/orion"
    assert "# Orion managed launcher" in launcher.read_text()
    assert trace.read_text().splitlines()[-1] == "orion:model install embeddings"

    launcher.write_text('#!/usr/bin/env bash\nexec /old/scripts/orion "$@"\n')
    legacy = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert legacy.returncode == 0
    assert "# Orion managed launcher" in launcher.read_text()
    launcher.write_text("# unrelated launcher\n")
    unrelated = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    assert unrelated.returncode != 0
    assert "Refusing to overwrite unrelated launcher" in unrelated.stderr
    assert "Installed Orion" not in unrelated.stdout


def test_version_is_wheel_source_and_cli_output(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from orion import cli
    from orion._version import __version__

    assert (
        f'__version__ = "{__version__}"'
        in (REPOSITORY / "backend/src/orion/_version.py").read_text()
    )
    monkeypatch.setattr(cli.sys, "argv", ["orion", "--version"])
    cli.main()
    assert capsys.readouterr().out.strip() == f"Orion {__version__}"
