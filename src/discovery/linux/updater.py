#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

RAW = ROOT / "stable_store/linux/raw/osquery.json"
INVENTORY = ROOT / "stable_store/linux/inventory.json"


def run(cmd):
    print(f"> {' '.join(map(str, cmd))}")
    subprocess.run(cmd, check=True)


def main():
    run(
        [
            sys.executable,
            str(Path(__file__).parent / "collector.py"),
            "-o",
            str(RAW),
        ]
    )

    run(
        [
            sys.executable,
            str(Path(__file__).parent / "transformer.py"),
            str(RAW),
            "-o",
            str(INVENTORY),
        ]
    )

    print(f"\nLinux inventory updated: {INVENTORY}")


if __name__ == "__main__":
    main()
