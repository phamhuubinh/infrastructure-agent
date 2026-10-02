"""Native Windows scenarios used by both source and release smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def preserve_user_path():
    """Restore exact registry value/type even if an installer exits PowerShell."""
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        access=winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
    ) as key:
        try:
            original = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            original = None
        try:
            yield
        finally:
            if original is None:
                try:
                    winreg.DeleteValue(key, "Path")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, "Path", 0, original[1], original[0])


def install(
    bundle: Path, root: Path, prefix: Path, env: dict[str, str], *, source: bool
) -> None:
    cli = prefix / ".venv/Scripts/orion.exe"
    python = prefix / ".venv/Scripts/python.exe"
    launcher = root / "local app data/Orion/bin/orion.cmd"
    env.update(
        LOCALAPPDATA=str(root / "local app data"),
        ORION_SMOKE_PREFIX=str(prefix),
        ORION_SMOKE_SOURCE="1" if source else "0",
        ORION_SMOKE_INSTALLER=str(bundle / "install.ps1"),
    )
    # First run discovers 3.12 via py/python; second discovers the existing venv.
    env.pop("ORION_PYTHON", None)
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(__file__).with_name("installer-check.ps1")),
    ]
    with preserve_user_path():
        created = None
        launcher_content = None
        for attempt in range(2):
            subprocess.run(command, cwd=root, env=env, check=True)
            assert cli.is_file() and launcher.is_file()
            current = (
                python.stat().st_mtime_ns,
                (prefix / ".venv/pyvenv.cfg").read_bytes(),
            )
            if attempt:
                assert current == created, "Installer recreated the venv on rerun"
                assert launcher.read_bytes() == launcher_content, (
                    "Launcher changed on rerun"
                )
            created = current
            launcher_content = launcher.read_bytes()
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import sys; assert sys.version_info[:2] == (3, 12)",
                ],
                cwd=root,
                env=env,
                check=True,
            )
        trace = Path(env["ORION_SMOKE_MODEL_TRACE"])
        assert trace.read_text().splitlines() == ["model install embeddings"] * 2

        direct = [
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
        if source:
            direct.append("-NoDev")
        env["ORION_PYTHON"] = sys.executable
        env["ORION_SMOKE_MODEL_FAIL"] = "1"
        launcher.unlink()
        failure = subprocess.run(
            direct, cwd=root, env=env, capture_output=True, text=True, check=False
        )
        assert failure.returncode != 0 and "Installed Orion" not in failure.stdout
        assert "deterministic model provisioning failure" in failure.stderr
        assert not launcher.exists(), "Failed provisioning published a launcher"
        env.pop("ORION_SMOKE_MODEL_FAIL")

        unrelated = b"@REM unrelated launcher\r\n"
        launcher.write_bytes(unrelated)
        refusal = subprocess.run(
            direct, cwd=root, env=env, capture_output=True, text=True, check=False
        )
        assert refusal.returncode != 0
        assert "Refusing to overwrite unrelated launcher" in refusal.stderr
        assert (
            "Installed Orion" not in refusal.stdout
            and launcher.read_bytes() == unrelated
        )
        assert trace.read_text().splitlines() == ["model install embeddings"] * 4
    print(
        "PASS: discovery, venv creation/reuse, spaces, rerun, provisioning failure, launcher refusal"
    )


def check_runtime_config(python: Path, root: Path, env: dict[str, str]) -> None:
    subprocess.run(
        [
            str(python),
            "-c",
            """
import os
from orion.access.remote import RemoteAccessConfig, hash_password
local = RemoteAccessConfig.from_environment()
assert not local.enabled and local.bind_host == '127.0.0.1'
os.environ.update(ORION_REMOTE_ACCESS='1', ORION_BIND_HOST='0.0.0.0',
                  ORION_PUBLIC_ORIGIN='https://orion.example.test',
                  ORION_AUTH_PASSWORD_HASH=hash_password('smoke-only-password'))
remote = RemoteAccessConfig.from_environment()
assert remote.enabled and remote.bind_host == '0.0.0.0'
assert remote.public_origin == 'https://orion.example.test'
""",
        ],
        cwd=root,
        env=env,
        check=True,
    )


def check_listener(pid: int, env: dict[str, str]) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 61888); "
                "if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1' -or "
                f"$listeners[0].OwningProcess -ne {pid}) "
                "{ throw 'Orion did not bind only loopback' }"
            ),
        ],
        env=env,
        check=True,
    )


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("Source smoke requires native Windows")
    # Reuse the release smoke's environment, model mock, UI and server probes.
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository / "scripts/release"))
    import smoke

    smoke.main(source=True)
