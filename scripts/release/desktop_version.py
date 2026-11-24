"""Allocate or validate a common increasing Windows version across both channels."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def parts(version: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(version)
    if not match or any(len(item) > 5 for item in match.groups()):
        raise ValueError("Expected a Windows X.Y.Z release version")
    major, minor, patch = map(int, match.groups())
    if max(major, minor, patch) > 65535:
        raise ValueError("A Windows version component exceeds 65535")
    return major, minor, patch


def allocate(base: str, tags: list[str], stable: str | None = None) -> str:
    published = []
    for tag in tags:
        match = re.fullmatch(r"(?:orion-preview-v|v)(\d+\.\d+\.\d+)", tag)
        if match:
            published.append(parts(match[1]))
    if stable is not None:
        value = parts(stable)
        if value != parts(base) or any(value <= previous for previous in published):
            raise ValueError(
                "Stable must match the source version and exceed every published version"
            )
        return stable
    major, minor, patch = max([parts(base), *published])
    if patch < 65535:
        return f"{major}.{minor}.{patch + 1}"
    if minor < 65535:
        return f"{major}.{minor + 1}.0"
    if major < 65535:
        return f"{major + 1}.0.0"
    raise ValueError("The Windows version space is exhausted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument(
        "releases", type=Path, help="GitHub release API pages via gh --slurp"
    )
    parser.add_argument("--stable")
    args = parser.parse_args()
    pages = json.loads(args.releases.read_text(encoding="utf-8"))
    tags = [release["tag_name"] for page in pages for release in page]
    print(allocate(args.base, tags, args.stable))


if __name__ == "__main__":
    main()
