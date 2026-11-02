"""Explicit immutable skill package reading with closed metadata and bounded paths."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal

import yaml
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken

from orion.contracts.skills import SkillDescriptor

MAX_PACKAGE_BYTES = 1_048_576
MAX_RESOURCE_BYTES = 262_144
MAX_PACKAGE_FILES = 64


class SkillPackageError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__("Skill package is unavailable: " + category)


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        result: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str) or key in result:
                raise ValueError("duplicate or non-text metadata key")
            result[key] = self.construct_object(value_node, deep=True)
        return result


@dataclass(frozen=True, repr=False)
class SkillPackage:
    descriptor: SkillDescriptor
    instructions: str
    resources: Mapping[str, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", MappingProxyType(dict(self.resources)))


def resource_path(value: str) -> str:
    if (
        not value
        or len(value.encode("utf-8")) > 512
        or any(c in value for c in "\\:\0")
        or value != PurePosixPath(value).as_posix()
        or value.startswith("/")
        or any(part.startswith(".") for part in value.split("/"))
    ):
        raise SkillPackageError("resource_path")
    return value


def _ordinary(path: Path, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    if (
        path.absolute() != path.resolve(strict=True)
        or stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise SkillPackageError("linked_or_special_path")
    return info


def package_digest(resources: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, data in sorted(resources.items()):
        digest.update(
            json.dumps([name, len(data)], ensure_ascii=True, separators=(",", ":")).encode()
        )
        digest.update(b"\0" + data + b"\0")
    return digest.hexdigest()


def parse_resources(
    resources: dict[str, bytes],
    source: Literal["bundled", "user", "project"],
    project_id: str | None = None,
) -> SkillPackage:
    try:
        if (
            not 0 < len(resources) <= MAX_PACKAGE_FILES
            or "SKILL.md" not in resources
            or sum(len(data) for data in resources.values()) > MAX_PACKAGE_BYTES
        ):
            raise SkillPackageError("package_bound")
        for name, data in resources.items():
            resource_path(name)
            if len(data) > MAX_RESOURCE_BYTES:
                raise SkillPackageError("resource_bound")
        text = resources["SKILL.md"].decode("utf-8-sig")
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            raise SkillPackageError("frontmatter")
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
        frontmatter = "".join(lines[1:end])
        body = "".join(lines[end + 1 :])
        if len(frontmatter.encode()) > 16_384 or not body.strip() or len(body.encode()) > 16_384:
            raise SkillPackageError("guidance_bound")
        for count, token in enumerate(yaml.scan(frontmatter)):
            if count > 2048 or isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise SkillPackageError("yaml_feature")
        raw = yaml.load(frontmatter, Loader=_UniqueLoader)
        if (
            not isinstance(raw, dict)
            or set(raw) != {"name", "description", "metadata"}
            or not isinstance(raw["metadata"], dict)
            or not {"version", "audience"} <= set(raw["metadata"])
            or not set(raw["metadata"])
            <= {"version", "audience", "scopes", "required_capabilities"}
            or raw["metadata"]["audience"] != "product"
            or raw["name"] in {"orion-refactor", "graphify"}
        ):
            raise SkillPackageError("metadata")
        metadata = raw["metadata"]
        descriptor = SkillDescriptor(
            name=raw["name"],
            description=raw["description"],
            version=metadata["version"],
            source=source,
            project_id=project_id,
            scopes=metadata.get("scopes", ("chat", "project", "device")),
            required_capabilities=metadata.get("required_capabilities", ()),
            package_sha256=package_digest(resources),
        )
        return SkillPackage(descriptor, body, dict(resources))
    except SkillPackageError:
        raise
    except (ValueError, TypeError, KeyError, StopIteration, RecursionError, yaml.YAMLError):
        raise SkillPackageError("invalid_package") from None


def read_package(
    root: Path, source: Literal["bundled", "user", "project"], project_id: str | None = None
) -> SkillPackage:
    """One operator-selected root only; never discover parents/global dev skills."""
    try:
        root = root.absolute()
        _ordinary(root, directory=True)
        resources: dict[str, bytes] = {}
        pending = [root]
        directories = 0
        total = 0
        while pending:
            directory = pending.pop()
            directories += 1
            if directories > 64:
                raise SkillPackageError("directory_bound")
            _ordinary(directory, directory=True)
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    relative = resource_path(path.relative_to(root).as_posix())
                    if len(PurePosixPath(relative).parts) > 8:
                        raise SkillPackageError("depth_bound")
                    info = path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        _ordinary(path, directory=True)
                        if directories + len(pending) >= 64:
                            raise SkillPackageError("directory_bound")
                        pending.append(path)
                        continue
                    _ordinary(path)
                    if len(resources) >= MAX_PACKAGE_FILES or info.st_size > MAX_RESOURCE_BYTES:
                        raise SkillPackageError("resource_bound")
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    try:
                        before = os.fstat(descriptor)
                        opened_path = _ordinary(path)
                        if (
                            (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)
                            or (before.st_dev, before.st_ino)
                            != (opened_path.st_dev, opened_path.st_ino)
                            or before.st_nlink != 1
                            or not stat.S_ISREG(before.st_mode)
                        ):
                            raise SkillPackageError("changed_during_open")
                        with os.fdopen(descriptor, "rb", closefd=False) as handle:
                            data = handle.read(MAX_RESOURCE_BYTES + 1)
                        after = os.fstat(descriptor)
                    finally:
                        os.close(descriptor)
                    if (
                        (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns)
                        != (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns)
                        or before.st_ino != info.st_ino
                        or before.st_dev != info.st_dev
                    ):
                        raise SkillPackageError("changed_during_read")
                    total += len(data)
                    if total > MAX_PACKAGE_BYTES or len(data) > MAX_RESOURCE_BYTES:
                        raise SkillPackageError("package_bound")
                    resources[relative] = data
        return parse_resources(resources, source, project_id)
    except SkillPackageError:
        raise
    except (OSError, ValueError):
        raise SkillPackageError("unreadable_package") from None
