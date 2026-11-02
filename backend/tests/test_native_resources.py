"""Shared API resources preserve package, scope and no-dispatch discovery boundaries."""

import io
import json
import stat
import struct
import zipfile

import httpx
import pytest
from test_command_service import Transport, call, terminal
from test_skill_packages import text

from orion._version import __version__
from orion.api.app import create_app
from orion.skills.archive import archive_resources
from orion.skills.packages import SkillPackageError


def package(entries=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries or [("SKILL.md", text()), ("reference.txt", "Tiếng Việt")]:
            archive.writestr(name, data)
    return output.getvalue()


@pytest.mark.parametrize(
    "entries",
    [
        [("../SKILL.md", text())],
        [("C:/SKILL.md", text())],
        [("SKILL.md", text()), ("SKILL.md", b"duplicate")],
        [("SKILL.md", text()), ("a", b"file"), ("a/b", b"child")],
        [("SKILL.md", text()), ("big.txt", b"x" * 262145)],
        [("/SKILL.md", text())],
    ],
)
def test_archive_rejects_unsafe_duplicate_special_and_bounded_resources(entries):
    with pytest.raises(SkillPackageError):
        archive_resources(package(entries))


def test_archive_rejects_unix_links_and_non_zip():
    item = zipfile.ZipInfo("SKILL.md")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(SkillPackageError):
        archive_resources(package([(item, b"outside")]))
    with pytest.raises(SkillPackageError):
        archive_resources(b"not a zip")
    # ZipFile.writestr normalizes NUL names before writing; mutate the on-wire
    # central/local names to exercise a genuinely hostile uploaded archive.
    with pytest.raises(SkillPackageError):
        archive_resources(
            package([("SKILL.mdXsuffix", text())]).replace(b"SKILL.mdXsuffix", b"SKILL.md\0suffix")
        )


def test_archive_rejects_malformed_deflate_stream_without_internal_error():
    data = bytearray(package())
    name_length, extra_length = struct.unpack_from("<HH", data, 26)
    data[30 + name_length + extra_length] = 7  # Invalid DEFLATE block type.
    with pytest.raises(SkillPackageError, match="invalid_archive"):
        archive_resources(bytes(data))


@pytest.mark.anyio
async def test_skill_api_installs_bytes_preserves_disabled_update_and_project_scope(tmp_path):
    api = create_app(tmp_path / "orion.db")
    app = api.state.application
    session = app.store.create_session()
    project = app.store.create_project("Project")["project_id"]
    project_session = app.store.create_session(project_id=project)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            response = await http.post(
                "/api/skills/packages",
                content=package(),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 201, response.text
            first = response.json()
            assert first["name"] == "fixture-skill"
            response = await http.patch(
                "/api/skills/fixture-skill", json={"source": "user", "enabled": False}
            )
            assert response.status_code == 204
            response = await http.post(
                "/api/skills/packages",
                content=package([("SKILL.md", text().replace(b'"1.0.0"', b'"1.1.0"'))]),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 201 and not response.json()["enabled"]
            assert response.json()["package_sha256"] != first["package_sha256"]
            assert (await http.delete("/api/skills/fixture-skill?source=user")).status_code == 204
            response = await http.post(
                f"/api/skills/packages?source=project&project_id={project}",
                content=package(),
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 201
            regular = (await http.get(f"/api/sessions/{session}/skills")).json()
            scoped = (await http.get(f"/api/sessions/{project_session}/skills")).json()
            assert "fixture-skill" not in {row["name"] for row in regular}
            assert "fixture-skill" in {row["name"] for row in scoped}
            assert (
                await http.post("/api/skills/packages", json={"path": "F:/secret"})
            ).status_code == 415
            assert (
                await http.post(
                    "/api/skills/packages",
                    content=package([("SKILL.md", text().replace(b"fixture-skill", b"graphify"))]),
                    headers={"Content-Type": "application/octet-stream"},
                )
            ).status_code == 422
            foreign = app.store.create_session(principal_id="other")
            assert (await http.get(f"/api/sessions/{foreign}/skills")).status_code == 404
    finally:
        app.store.close()


@pytest.mark.anyio
async def test_command_resources_use_actual_scope_and_never_expose_script_or_cached_output(
    tmp_path,
):
    api = create_app(tmp_path / "orion.db")
    app = api.state.application
    assert app.commands is not None
    original = app.commands
    transport = Transport(app.store)
    original.transport = transport
    invocation = call(app.store)
    try:
        first = await original.run(invocation)
        await terminal(original, invocation, first.command_id)
        session = invocation.runtime_scope.session_id
        other = app.store.create_session()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            response = await http.get(f"/api/sessions/{session}/commands")
            assert response.status_code == 200
            row = response.json()[0]
            assert row["command_id"] == first.command_id and not row["output_available"]
            assert "private-output-marker" not in response.text and '"command"' not in response.text
            before = len(transport.calls)
            for suffix in ("", "/cancel"):
                response = await http.request(
                    "POST" if suffix else "GET",
                    f"/api/sessions/{other}/commands/{first.command_id}{suffix}",
                )
                assert response.status_code == 404
            assert len(transport.calls) == before
            response = await http.get(f"/api/sessions/{session}/commands/{first.command_id}")
            assert (
                response.status_code == 200 and "private-output-marker" in response.json()["stdout"]
            )
            response = await http.post(
                f"/api/sessions/{session}/commands/{first.command_id}/cancel"
            )
            assert response.status_code == 200
            assert (await http.get(f"/api/sessions/{session}/commands?limit=65")).status_code == 422
            assert (
                await http.post(f"/api/sessions/{session}/commands", json={"command": "execute"})
            ).status_code == 405
    finally:
        await original.close()
        await transport.executor.close()
        app.store.close()


@pytest.mark.anyio
async def test_version_doctor_and_target_discovery_are_configuration_observations(tmp_path):
    api = create_app(tmp_path / "orion.db")
    app = api.state.application
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            response = await http.get("/api/version")
            assert response.status_code == 200 and response.json()["version"] == __version__
            assert api.openapi()["info"]["version"] == __version__
            doctor = (await http.get("/api/doctor")).json()
            assert doctor["observation"] == "configuration" and doctor["active_requests"] == 0
            assert not doctor["model_profile_configured"]
            assert (await http.get("/api/targets")).json() == []
            output = json.dumps(doctor)
            assert "credential" not in output and str(tmp_path) not in output
    finally:
        app.store.close()
