"""Isolated installer/CLI smoke that never touches an Orion user prefix or data."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    repository = Path(__file__).parents[2]
    with tempfile.TemporaryDirectory(prefix="orion-operations-") as temporary:
        root = Path(temporary)
        prefix, data = root / "install", root / "data"
        environment = {
            **os.environ,
            "HOME": str(root / "home"),
            "ORION_PYTHON": sys.executable,
            "ORION_TEST_SECRET_TOKEN": "operations-marker-secret",
        }
        subprocess.run(
            [str(repository / "install.sh"), "--prefix", str(prefix), "--no-dev"],
            check=True,
            cwd=repository,
            env=environment,
            stdout=subprocess.DEVNULL,
        )
        command = [str(prefix / ".venv" / "bin" / "orion")]
        help_output = subprocess.check_output([*command, "--help"], env=environment, text=True)
        log_output = subprocess.check_output(
            [*command, "log", "--data-dir", str(data)], env=environment, text=True
        )
        if "web" not in help_output or "log" not in help_output:
            raise SystemExit("installed CLI did not expose web/log commands")
        if str(data / "orion.db") not in log_output:
            raise SystemExit("installed CLI did not use the isolated data directory")
        if "operations-marker-secret" in log_output:
            raise SystemExit("installed CLI exposed a configured marker secret")


if __name__ == "__main__":
    main()
