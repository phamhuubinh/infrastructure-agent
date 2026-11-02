"""Transactional owner catalogs, immutable revisions and managed-data round trip."""

import sqlite3

import pytest
from test_skill_packages import text

from orion.knowledge.blob_store import LocalBlobStore
from orion.persistence.backup import export_bundle, import_bundle
from orion.persistence.sqlite import SQLiteStore
from orion.skills.packages import parse_resources


def package(version="1.0.0", source="user", project=None):
    return parse_resources(
        {
            "SKILL.md": text().replace(b'"1.0.0"', ('"' + version + '"').encode()),
            "references/read.md": b"bounded resource",
        },
        source,
        project,
    )


def test_atomic_revision_lifecycle_and_pinned_content_collection(store):
    first, second = package(), package("1.1.0")
    store.install_skill(first, "owner", "workspace")
    store.install_skill(first, "owner", "workspace")
    store.install_skill(second, "owner", "workspace")
    assert store.skill_catalog("owner", "workspace")[0].version == "1.1.0"
    store.collect_unused_skills({first.descriptor.package_sha256})
    assert store.skill_package_resources(first.descriptor.package_sha256) == first.resources
    assert store.set_skill_enabled("owner", "workspace", "user", None, "fixture-skill", False)
    assert not store.skill_catalog("owner", "workspace")[0].enabled
    assert not store.remove_skill("other", "workspace", "user", None, "fixture-skill")
    assert store.remove_skill("owner", "workspace", "user", None, "fixture-skill")
    store.collect_unused_skills(set())
    assert not store._connection.execute("SELECT 1 FROM skill_packages").fetchone()
    assert not store._connection.execute("SELECT 1 FROM skill_resources").fetchone()


def test_catalog_ownership_project_identity_and_resource_integrity(store):
    project = package(source="project", project="project-a")
    store.install_skill(project, "owner", "workspace")
    assert store.skill_catalog("other", "workspace", "project-a") == []
    assert store.skill_catalog("owner", "other", "project-a") == []
    assert store.skill_catalog("owner", "workspace", "project-b") == []
    assert store.skill_catalog("owner", "workspace") == []
    assert store.skill_catalog("owner", "workspace", "project-a")[0].project_id == "project-a"
    with store._connection:
        store._connection.execute(
            "UPDATE skill_resources SET content=? WHERE path=?", (b"tampered", "references/read.md")
        )
    with pytest.raises(ValueError, match="integrity"):
        store.skill_package_resources(project.descriptor.package_sha256)


def test_failed_update_rolls_back_catalog_manifest_and_all_new_resources(store):
    first = package()
    store.install_skill(first, "owner", "workspace")
    second = parse_resources(
        {"SKILL.md": text().replace(b'"1.0.0"', b'"1.1.0"'), "blocked": b"new resource"}, "user"
    )
    with store._connection:
        store._connection.execute(
            "CREATE TRIGGER reject_fixture_resource BEFORE INSERT ON skill_resources "
            "WHEN NEW.path='blocked' BEGIN SELECT RAISE(ABORT,'fixture refusal'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="fixture refusal"):
        store.install_skill(second, "owner", "workspace")
    assert (
        store.skill_catalog("owner", "workspace")[0].package_sha256
        == first.descriptor.package_sha256
    )
    assert (
        store._connection.execute(
            "SELECT 1 FROM skill_packages WHERE digest=?", (second.descriptor.package_sha256,)
        ).fetchone()
        is None
    )
    assert store.skill_package_resources(first.descriptor.package_sha256) == first.resources


def test_managed_backup_restore_includes_installed_skill_resources_and_preferences(tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    database = root / "orion.db"
    LocalBlobStore(root / "blobs")
    original = SQLiteStore(database)
    skill = package()
    try:
        original.install_skill(skill, "local", "local", enabled=False)
    finally:
        original.close()
    destination = tmp_path / "backups"
    destination.mkdir()
    bundle = export_bundle(database, destination)
    restored_path = import_bundle(bundle, tmp_path / "restored")
    restored = SQLiteStore(restored_path)
    try:
        descriptor = restored.skill_catalog("local", "local")[0]
        assert (
            not descriptor.enabled and descriptor.package_sha256 == skill.descriptor.package_sha256
        )
        assert restored.skill_package_resources(descriptor.package_sha256) == skill.resources
    finally:
        restored.close()
