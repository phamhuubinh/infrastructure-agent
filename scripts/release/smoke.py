"""Exercise an extracted release archive outside the repository checkout."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


def main(*, source: bool = False) -> None:
    bundle = Path(sys.argv[1]).resolve()
    platform = "windows-x64" if source else sys.argv[2]
    if platform == "windows-x64":
        if sys.platform != "win32":
            raise SystemExit("Windows smoke requires native Windows")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
        import installer_smoke
    manifest = (
        None if source else json.loads((bundle / "release-manifest.json").read_text())
    )
    with tempfile.TemporaryDirectory(
        prefix="orion release smoke ", ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        mock = root / "model-mock"
        mock.mkdir()
        (mock / "sitecustomize.py").write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "if sys.argv[1:] == ['model', 'install', 'embeddings']:\n"
            " def no_download(*args, **kwargs):\n"
            "  raise RuntimeError('Model network access is forbidden in smoke tests')\n"
            " import urllib.request\n"
            " urllib.request.urlopen = no_download\n"
            " try:\n"
            "  import orion.knowledge.local_embeddings as e\n"
            " except Exception:\n"
            "  os._exit(86)\n"
            " def install_model(*args, **kwargs):\n"
            "  with Path(os.environ['ORION_SMOKE_MODEL_TRACE']).open('a') as trace:\n"
            "   trace.write('model install embeddings\\n')\n"
            "  if os.environ.get('ORION_SMOKE_MODEL_FAIL') == '1':\n"
            "   raise RuntimeError('deterministic model provisioning failure')\n"
            "  return 'verified-test-cache'\n"
            " e.urlopen = no_download\n"
            " e.install_model = install_model\n"
        )
        forbidden = root / "forbidden-tools"
        forbidden.mkdir()
        marker = root / "forbidden-tool-invoked"
        names = (
            ("xdg-open", "gio", "open")
            if source
            else ("git", "node", "npm", "xdg-open", "gio", "open")
        )
        for name in names:
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
        for key in list(env):
            if key.startswith("ORION_"):
                env.pop(key)
        env.update(
            HOME=str(root / "home"),
            ORION_DATA_DIR=str(root / "data"),
            ORION_PYTHON=sys.executable,
            PYTHONPATH=str(mock),
            ORION_INTERNAL_NO_BROWSER="1",
            ORION_FORBIDDEN_TOOL_MARKER=str(marker),
            ORION_SMOKE_MODEL_TRACE=str(root / "model-trace"),
            PATH=str(forbidden) + os.pathsep + os.environ["PATH"],
        )
        (root / "home").mkdir()
        prefix = root / "install prefix with spaces"
        env["ORION_UI_DIR"] = str(prefix / ".orion-ui")
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
            installer_smoke.install(bundle, root, prefix, env, source=source)
            cli = prefix / ".venv/Scripts/orion.exe"
            launcher = root / "local app data/Orion/bin/orion.cmd"
            installer_smoke.check_runtime_config(
                prefix / ".venv/Scripts/python.exe", root, env
            )
        for _ in range(2 if platform == "linux-x86_64" else 0):
            subprocess.run(installer, cwd=root, env=env, check=True)
            assert cli.is_file() and launcher.is_file()
        if platform == "linux-x86_64":
            assert (
                Path(env["ORION_SMOKE_MODEL_TRACE"]).read_text().splitlines()
                == ["model install embeddings"] * 2
            )
        installed_ui = prefix / ".orion-ui"
        assert (installed_ui / "_shell.html").is_file()
        if manifest is not None:
            assert {
                path.relative_to(installed_ui).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in installed_ui.rglob("*")
                if path.is_file()
            } == manifest["ui_files"]
            output = subprocess.check_output(
                [str(cli), "--version"], cwd=root, env=env, text=True
            )
            assert output.strip() == f"Orion {manifest['version']}"
        subprocess.run([str(cli), "help"], cwd=root, env=env, check=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 61888))
        server = subprocess.Popen([str(cli), "web"], cwd=root, env=env)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f"Orion exited early: {server.returncode}")
                try:
                    with urlopen(
                        "http://127.0.0.1:61888/api/health", timeout=1
                    ) as response:
                        health = json.load(response)
                        assert (
                            health["identity"] == "orion" and health["status"] == "ok"
                        )
                    with urlopen("http://127.0.0.1:61888/", timeout=1) as response:
                        assert response.status == 200
                        assert (
                            response.read()
                            == (installed_ui / "_shell.html").read_bytes()
                        )
                    assets = list((installed_ui / "assets").glob("*.js"))
                    assert assets, "Packaged UI has no JavaScript assets"
                    with urlopen(
                        f"http://127.0.0.1:61888/assets/{assets[0].name}", timeout=1
                    ) as response:
                        assert response.read() == assets[0].read_bytes()
                    if platform == "windows-x64":
                        installer_smoke.check_listener(server.pid, env)
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Orion health endpoint did not start")
        finally:
            if platform == "windows-x64":
                # Stop Python children behind Windows console/venv launchers too.
                subprocess.run(
                    ["taskkill", "/PID", str(server.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        print("PASS: health without login, packaged HTML/assets, native runtime")
        assert not marker.exists(), (
            "Release smoke invoked a forbidden build tool or browser opener"
        )


if __name__ == "__main__":
    main()
