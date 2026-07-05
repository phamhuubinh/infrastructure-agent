#!/usr/bin/env python3

import subprocess
import sys


def run(cmd):
    print(f"> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    raw = "result.json"
    knowledge = "knowledge_store.json"

    run([
        sys.executable,
        "collect_osquery.py",
        "-o",
        raw,
    ])

    run([
        sys.executable,
        "build_knowledge_store.py",
        raw,
        "-o",
        knowledge,
    ])

    print(f"\nKnowledge Store updated: {knowledge}")


if __name__ == "__main__":
    main()
