"""Product package trust/path/metadata limits; never execute packaged scripts."""

import os
from pathlib import Path

import pytest

from orion.contracts import RuntimeScope
from orion.skills.packages import SkillPackageError, parse_resources, read_package, resource_path


def text(name="fixture-skill", extra="", audience="product"):
    return f"""---
name: {name}
description: Scoped fixture guidance
metadata:
  version: "1.0.0"
  audience: {audience}
{extra}---
# Guidance
Read evidence and obey the user's scope; scripts need canonical authorization.
""".encode()


def test_wide_directory_enumeration_is_bounded_before_queuing_all_entries(tmp_path):
    (tmp_path / "SKILL.md").write_bytes(text())
    for index in range(65):
        (tmp_path / f"directory-{index}").mkdir()
    with pytest.raises(SkillPackageError, match="directory_bound"):
        read_package(tmp_path, "user")


def test_bundled_product_packages_validate_and_development_skill_is_excluded():
    root = Path(__file__).parents[2] / "skills"
    packages = [read_package(path, "bundled") for path in sorted((root / "builtin").iterdir())]
    assert {p.descriptor.name for p in packages} == {
        "windows-linux-ops",
        "project-research",
        "mcp-workflows",
    }
    research = next(p for p in packages if p.descriptor.name == "project-research")
    assert not research.descriptor.applies_to(
        RuntimeScope(
            session_id="device", principal_id="local", workspace_id="local", endpoint_id="a" * 32
        )
    )
    with pytest.raises(SkillPackageError):
        read_package(root / "development/orion-refactor", "user")


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/etc/shadow",
        "C:/secret",
        "a\\b",
        ".env",
        "references/.git/key",
        "references//a.md",
        "a/./b.md",
        "a/../b.md",
        "a\0b",
    ],
)
def test_resource_paths_never_authorize_other_files(path):
    with pytest.raises(SkillPackageError):
        resource_path(path)


@pytest.mark.parametrize(
    "data",
    [
        b"No frontmatter",
        text(audience="development"),
        text(name="orion-refactor"),
        text(name="graphify"),
        text().replace(b"name: fixture-skill", b"name: fixture-skill\nname: other"),
        text().replace(
            b"description: Scoped fixture guidance", b"description: &x Scoped\nother: *x"
        ),
        text().replace(b"description: Scoped fixture guidance", b"description: !!str Scoped"),
        text().replace(b'"1.0.0"', b'"unknown"'),
        text(extra="  source: project\n"),
        text(extra="  scopes: [chat, chat]\n"),
    ],
)
def test_closed_metadata_no_yaml_alias_tag_or_runtime_authority(data):
    with pytest.raises(SkillPackageError):
        parse_resources({"SKILL.md": data}, "user")


def test_package_digest_binds_every_resource_and_scope_is_not_self_declared(tmp_path):
    (tmp_path / "SKILL.md").write_bytes(
        text(extra="  required_capabilities: [system.command.run]\n")
    )
    script = tmp_path / "script.ps1"
    script.write_text("Write-Output 'resource only, never automatically executed'")
    first = read_package(tmp_path, "user")
    script.write_text("Write-Output 'changed'")
    changed = read_package(tmp_path, "user")
    assert first.descriptor.package_sha256 != changed.descriptor.package_sha256
    project = read_package(tmp_path, "project", "project-a")
    assert project.descriptor.applies_to(
        RuntimeScope(
            session_id="a", principal_id="local", workspace_id="local", project_id="project-a"
        )
    )
    assert not project.descriptor.applies_to(
        RuntimeScope(
            session_id="b", principal_id="local", workspace_id="local", project_id="project-b"
        )
    )
    with pytest.raises(SkillPackageError):
        read_package(tmp_path, "project")


def test_hardlink_private_hidden_and_size_limits_refuse_package(tmp_path):
    (tmp_path / "SKILL.md").write_bytes(text())
    outside = tmp_path.parent / "unrelated-secret"
    outside.write_text("preserve")
    os.link(outside, tmp_path / "linked-resource")
    with pytest.raises(SkillPackageError):
        read_package(tmp_path, "user")
    (tmp_path / "linked-resource").unlink()
    (tmp_path / ".env").write_text("never included")
    with pytest.raises(SkillPackageError):
        read_package(tmp_path, "user")
    with pytest.raises(SkillPackageError):
        parse_resources({"SKILL.md": text(), "big": b"x" * 262_145}, "user")
    assert outside.read_text() == "preserve"
