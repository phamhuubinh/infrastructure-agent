"""Exercise an extracted release archive outside the repository checkout."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


def main() -> None:
    bundle = Path(sys.argv[1]).resolve()
    platform = sys.argv[2]
    manifest = json.loads((bundle / "release-manifest.json").read_text())
    with tempfile.TemporaryDirectory(
        prefix="orion release smoke ", ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        mock = root / "model-mock"
        mock.mkdir()
        (mock / "sitecustomize.py").write_text(
            "try:\n"
            " import orion.knowledge.local_embeddings as e\n"
            " e.install_model = lambda: 'verified-test-cache'\n"
            "except ImportError:\n pass\n"
        )
        forbidden = root / "forbidden-tools"
        forbidden.mkdir()
        marker = root / "forbidden-tool-invoked"
        for name in ("git", "node", "npm", "xdg-open", "gio", "open"):
            if platform == "windows-x64":
                (forbidden / f"{name}.cmd").write_text(
                    '@echo off\r\necho invoked>>"%ORION_FORBIDDEN_TOOL_MARKER%"\r\nexit /b 87\r\n'
                )
            else:
                wrapper = forbidden / name
                wrapper.write_text(
                    '#!/usr/bin/env sh\nprintf "invoked\n" >> "$ORION_FORBIDDEN_TOOL_MARKER"\nexit 87\n'
                )
                wrapper.chmod(0o755)
        env = os.environ.copy()
        env.update(
            HOME=str(root / "home"),
            ORION_DATA_DIR=str(root / "data"),
            ORION_PYTHON=sys.executable,
            PYTHONPATH=str(mock),
            ORION_INTERNAL_NO_BROWSER="1",
            ORION_FORBIDDEN_TOOL_MARKER=str(marker),
            PATH=str(forbidden) + os.pathsep + os.environ["PATH"],
        )
        (root / "home").mkdir()
        prefix = root / "install prefix with spaces"
        if platform == "linux-x86_64":
            env["XDG_BIN_HOME"] = str(root / "bin")
            installer = [
                "bash",
                str(bundle / "install.sh"),
                "--prefix",
                str(prefix),
                "--global-launcher",
            ]
            cli = prefix / ".venv/bin/orion"
            launcher = root / "bin/orion"
        else:
            env["LOCALAPPDATA"] = str(root / "local app data")
            installer = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(bundle / "install.ps1"),
                "-Prefix",
                str(prefix),
                "-GlobalLauncher",
            ]
            cli = prefix / ".venv/Scripts/orion.exe"
            launcher = root / "local app data/Orion/bin/orion.cmd"
        for _ in range(2):
            subprocess.run(installer, cwd=root, env=env, check=True)
            assert cli.is_file() and launcher.is_file()
            installed_ui = prefix / ".orion-ui"
            assert (installed_ui / "_shell.html").is_file()
            assert {
                path.relative_to(installed_ui).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in installed_ui.rglob("*")
                if path.is_file()
            } == manifest["ui_files"]
            subprocess.run([str(cli), "help"], cwd=root, env=env, check=True)
            output = subprocess.check_output(
                [str(cli), "--version"], cwd=root, env=env, text=True
            )
            assert output.strip() == f"Orion {manifest['version']}"
            if platform == "windows-x64":
                user_path = subprocess.check_output(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "[Environment]::GetEnvironmentVariable('Path', 'User')",
                    ],
                    cwd=root,
                    env=env,
                    text=True,
                )
                assert str(launcher.parent).lower() in {
                    entry.strip().lower() for entry in user_path.split(";")
                }
        server = subprocess.Popen([str(cli), "web"], cwd=root, env=env)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f"Orion exited early: {server.returncode}")
                try:
                    with urlopen(
                        "http://127.0.0.1:61888/api/health", timeout=1
                    ) as response:
                        assert json.load(response)["identity"] == "orion"
                    with urlopen("http://127.0.0.1:61888/", timeout=1) as response:
                        assert response.status == 200 and response.read()
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Orion health endpoint did not start")
        finally:
            server.terminate()
            server.wait(timeout=10)
        assert not marker.exists(), (
            "Release smoke invoked a forbidden build tool or browser opener"
        )


if __name__ == "__main__":
    main()
