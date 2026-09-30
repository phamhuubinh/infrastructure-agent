"""Installer contracts exercised without installing dependencies or downloading E5."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).parents[2]


def _mock_linux_install(
    tmp_path: Path, *, model_exit: int = 0
) -> tuple[subprocess.CompletedProcess[str], str]:
    prefix = tmp_path / "prefix with spaces"
    scripts = prefix / ".venv" / "bin"
    scripts.mkdir(parents=True, exist_ok=True)
    trace = tmp_path / "installer.trace"
    python = scripts / "python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-c" ]]; then exit 0; fi\n'
        'printf "python:%s\\n" "$*" >> "$ORION_INSTALL_TRACE"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    orion = scripts / "orion"
    orion.write_text(
        "#!/usr/bin/env bash\n"
        'printf "orion:%s\\n" "$*" >> "$ORION_INSTALL_TRACE"\n'
        'if [[ "$ORION_TEST_MODEL_EXIT" != 0 ]]; then exit "$ORION_TEST_MODEL_EXIT"; fi\n'
        'echo "embeddings: installed"\n',
        encoding="utf-8",
    )
    orion.chmod(0o755)
    global_orion = tmp_path / "orion"
    global_orion.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    global_orion.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "ORION_INSTALL_TRACE": str(trace),
        "ORION_TEST_MODEL_EXIT": str(model_exit),
    }
    environment.pop("ORION_PYTHON", None)
    result = subprocess.run(
        [str(REPOSITORY / "install.sh"), "--prefix", str(prefix), "--no-dev"],
        cwd=REPOSITORY,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, trace.read_text(encoding="utf-8")


def test_linux_install_provisions_after_ui_and_reuses_successful_rerun(tmp_path: Path) -> None:
    first, first_trace = _mock_linux_install(tmp_path)
    assert first.returncode == 0
    assert "Installed Orion" in first.stdout
    assert first_trace.splitlines() == [
        f"python:-m pip install -e {REPOSITORY / 'backend'}",
        f"python:-m orion.ui_package --repository {REPOSITORY} "
        f"--destination {tmp_path / 'prefix with spaces' / '.orion-ui'} --npm-ci",
        "orion:model install embeddings",
    ]

    second, second_trace = _mock_linux_install(tmp_path)
    assert second.returncode == 0
    assert "embeddings: installed" in second.stdout
    assert second_trace.splitlines()[-3:] == first_trace.splitlines()


def test_linux_install_fails_before_success_when_model_provisioning_fails(tmp_path: Path) -> None:
    result, trace = _mock_linux_install(tmp_path, model_exit=23)
    assert result.returncode == 23
    assert trace.splitlines()[-1] == "orion:model install embeddings"
    assert "Installed Orion" not in result.stdout


def test_windows_installer_core_contracts() -> None:
    script = (REPOSITORY / "install.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetFullPath($PSScriptRoot)" in script
    assert "Scripts\\python.exe" in script
    assert "Scripts\\orion.exe" in script
    assert "ORION_PYTHON" in script
    assert "@('-3.12')" in script
    assert "Python 3.12 or newer is required" in script
    assert "Node.js >=22.12" in script
    assert "--npm-ci" in script
    assert script.index("'orion.ui_package'") < script.index("@('model', 'install', 'embeddings')")
    assert script.index("@('model', 'install', 'embeddings')") < script.index("Installed Orion in")


def test_windows_launcher_and_path_contracts() -> None:
    script = (REPOSITORY / "install.ps1").read_text(encoding="utf-8")
    assert "Join-Path $localAppData 'Orion\\bin'" in script
    assert "Join-Path $launcherDirectory 'orion.cmd'" in script
    assert "$OrionExecutable.Replace('%', '%%')" in script
    assert '`"$escapedExecutable`" %*' in script
    assert "setlocal DisableDelayedExpansion" in script
    assert "if ($firstLine -cne '@REM Orion managed launcher')" in script
    assert "Refusing to overwrite unrelated launcher" in script
    assert "if ($found) { continue }" in script
    assert "if (-not $found) { $userEntries.Add($launcherDirectory) }" in script
    assert "-not (Test-PathEntryMatchesDirectory $entry $launcherDirectory)" in script
    assert "$env:PATH = (@($launcherDirectory) + $processEntries.ToArray()) -join ';'" in script
    assert "[Environment]::SetEnvironmentVariable('Path', $updatedUserPath, 'User')" in script
    assert "if (-not $prefixWasExplicit -or $GlobalLauncher)" in script


@pytest.mark.parametrize("installer", ("install.sh", "install.ps1"))
def test_installers_leave_semantic_activation_and_indexing_explicit(installer: str) -> None:
    script = (REPOSITORY / installer).read_text(encoding="utf-8")
    assert "semantic-index" not in script
    assert "ORION_KNOWLEDGE_SEMANTIC_SEARCH" not in script
