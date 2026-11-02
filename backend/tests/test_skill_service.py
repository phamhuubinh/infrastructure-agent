"""Pinned request catalogs and actual owner/surface boundaries for product guidance."""

import pytest
from test_skill_packages import text

from orion.contracts import RuntimeScope
from orion.skills.service import SkillError, SkillService


def scope_request(store, **identity):
    session = store.create_session(**identity)
    scope = RuntimeScope(session_id=session, principal_id="local", workspace_id="local", **identity)
    return scope, store.create_request(session)


def install(service, tmp_path, version="1.0.0", **kwargs):
    root = tmp_path / version
    root.mkdir(exist_ok=True)
    (root / "SKILL.md").write_bytes(text().replace(b'"1.0.0"', ('"' + version + '"').encode()))
    (root / "reference.txt").write_text("你好 resource", encoding="utf-8")
    (root / "binary.bin").write_bytes(b"\xff")
    return service.install(root, **{"source": "user", **kwargs})


def test_request_pins_revision_preferences_and_capabilities_until_cleanup(store, tmp_path):
    service = SkillService(store)
    first = install(service, tmp_path)
    scope, request = scope_request(store)
    service.begin_request(request, scope, "/skill fixture-skill\nDo the scoped work")
    assert "Selected skill guidance fixture-skill" in service.context(request, scope)
    service.set_enabled(first.name, "user", False)
    second = install(service, tmp_path, "1.1.0")
    assert not second.enabled
    assert (
        service.load(request, scope, first.name, first.package_sha256).descriptor.version == "1.0.0"
    )
    service.remove(first.name, "user")
    assert store.skill_package_resources(first.package_sha256)
    other = store.create_request(scope.session_id)
    service.begin_request(other, scope, "/skill fixture-skill")
    assert "not_found" in service.context(other, scope)
    service.end_request(request)
    with pytest.raises(ValueError):
        store.skill_package_resources(first.package_sha256)
    service.end_request(other)
    assert not service.requests


def test_actual_session_scope_and_project_device_isolation(store, tmp_path):
    service = SkillService(store)
    project = store.create_project("Private project")["project_id"]
    descriptor = install(service, tmp_path, source="project", project_id=project)
    scope, request = scope_request(store, project_id=project)
    service.begin_request(request, scope, "work")
    assert descriptor.name in service.catalog(scope)
    device, device_request = scope_request(store, endpoint_id="a" * 32)
    service.begin_request(device_request, device, "work")
    assert descriptor.name not in service.catalog(device)
    assert "project-research" not in service.catalog(device)
    with pytest.raises(SkillError, match="scope"):
        service.context(request, scope.model_copy(update={"principal_id": "other"}))
    with pytest.raises(SkillError, match="request"):
        service.context(request, device)
    with pytest.raises(SkillError, match="not_found"):
        service.load(device_request, device, descriptor.name, descriptor.package_sha256)


def test_resource_reads_are_bounded_utf8_and_never_leave_package(store, tmp_path):
    service = SkillService(store)
    descriptor = install(service, tmp_path)
    scope, request = scope_request(store)
    service.begin_request(request, scope, "work")
    args = (request, scope, descriptor.name, descriptor.package_sha256)
    first = service.read(*args, "reference.txt", length=4)
    assert first["text"] == "你" and first["next_offset"] == 3
    with pytest.raises(SkillError, match="page_too_small"):
        service.read(*args, "reference.txt", length=1)
    assert service.read(*args, "reference.txt", offset=3)["text"] == "好 resource"
    for path, offset, category in [
        ("../secret", 0, "resource_path"),
        ("binary.bin", 0, "binary_or_cursor"),
        ("reference.txt", 1, "binary_or_cursor"),
    ]:
        with pytest.raises(SkillError, match=category):
            service.read(*args, path, offset=offset)
    with pytest.raises(SkillError, match="version_mismatch"):
        service.load(request, scope, descriptor.name, "0" * 64)


def test_missing_capability_stays_missing_in_existing_request(store):
    service = SkillService(store)
    scope, request = scope_request(store)
    descriptor = service.catalog(scope)["mcp-workflows"]
    service.begin_request(request, scope, "/skill mcp-workflows")
    assert "missing_capability" in service.context(request, scope)
    service.capabilities = frozenset(descriptor.required_capabilities)
    with pytest.raises(SkillError, match="missing_capability"):
        service.load(request, scope, descriptor.name, descriptor.package_sha256)
    new_request = store.create_request(scope.session_id)
    service.begin_request(new_request, scope, "/skill mcp-workflows")
    assert "Selected skill guidance mcp-workflows" in service.context(new_request, scope)
