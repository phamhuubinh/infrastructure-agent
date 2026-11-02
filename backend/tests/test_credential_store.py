from __future__ import annotations

import base64
import json
import os
import stat

import httpx
import pytest
from pydantic import SecretStr

from orion.api.app import create_app
from orion.models.credential_store import ProtectedFileCredentialStore, credentials_for_database
from orion.models.credentials import CredentialResolutionError


def test_current_platform_protected_store_roundtrip_restart_and_delete(tmp_path):
    root = tmp_path / "provider-credentials"
    store = ProtectedFileCredentialStore(root)
    reference = store.put(SecretStr("fixture-private-provider-key"))
    assert reference.startswith("secret:")
    path = root / (reference[7:] + ".json")
    record = json.loads(path.read_bytes())
    if os.name == "nt":
        assert record["kind"] == "windows-dpapi-v1"
        assert b"fixture-private-provider-key" not in base64.b64decode(record["payload"])
    else:
        assert record["kind"] == "posix-owned-file-v1"
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (
        ProtectedFileCredentialStore(root).resolve(reference).get_secret_value()
        == "fixture-private-provider-key"
    )
    store.delete(reference)
    with pytest.raises(CredentialResolutionError):
        store.resolve(reference)


@pytest.mark.parametrize(
    "reference", ["secret:../../outside", "secret:" + "A" * 32, "env:KEY", "private-ref"]
)
def test_invalid_reference_does_not_touch_files_or_echo_input(tmp_path, reference):
    root = tmp_path / "absent"
    store = ProtectedFileCredentialStore(root)
    with pytest.raises(CredentialResolutionError) as caught:
        store.resolve(reference)
    assert reference not in str(caught.value)
    assert not root.exists()


def test_corrupt_protected_record_fails_without_plaintext_fallback_or_mutation(tmp_path):
    root = tmp_path / "provider-credentials"
    store = ProtectedFileCredentialStore(root)
    reference = store.put(SecretStr("fixture-private-key"))
    path = root / (reference[7:] + ".json")
    original = path.read_bytes()
    record = json.loads(original)
    payload = bytearray(base64.b64decode(record["payload"]))
    payload[0] ^= 1
    record["payload"] = base64.b64encode(payload).decode("ascii")
    path.write_text(json.dumps(record), encoding="utf-8")
    corrupt = path.read_bytes()
    with pytest.raises(CredentialResolutionError) as caught:
        store.resolve(reference)
    assert "fixture-private-key" not in str(caught.value)
    assert path.read_bytes() == corrupt
    path.write_bytes(original)
    assert store.resolve(reference).get_secret_value() == "fixture-private-key"


@pytest.mark.skipif(
    os.name == "nt", reason="Requires native POSIX ownership/permission enforcement"
)
def test_posix_store_refuses_broad_permissions(tmp_path):
    root = tmp_path / "provider-credentials"
    store = ProtectedFileCredentialStore(root)
    reference = store.put(SecretStr("fixture-private-key"))
    path = root / (reference[7:] + ".json")
    path.chmod(0o644)
    with pytest.raises(CredentialResolutionError):
        store.resolve(reference)
    path.chmod(0o600)
    root.chmod(0o755)
    with pytest.raises(CredentialResolutionError):
        store.resolve(reference)
    root.chmod(0o700)


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows DPAPI")
def test_windows_protection_failure_never_writes_plaintext(tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        raise CredentialResolutionError("Protection unavailable")

    monkeypatch.setattr("orion.models.credential_store._dpapi", failed)
    root = tmp_path / "absent"
    with pytest.raises(CredentialResolutionError):
        ProtectedFileCredentialStore(root).put(SecretStr("fixture-private-key"))
    assert not root.exists()


@pytest.mark.anyio
async def test_profile_api_can_bind_protected_reference_without_exposing_key(tmp_path):
    path = tmp_path / "application.db"
    app = create_app(path)
    resolver = credentials_for_database(path)
    reference = resolver.store.put(SecretStr("fixture-protected-api-key"))
    profile = {
        "profile_id": "protected",
        "provider_id": "openai_compatible",
        "protocol": "chat_completions",
        "endpoint": "http://fixture.test/v1",
        "model_id": "configured",
        "credential_ref": reference,
        "capabilities": {"streaming": True},
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/models",
                json={
                    "provider_type": "openai_compatible",
                    "base_url": profile["endpoint"],
                    "model_id": profile["model_id"],
                    "profile": profile,
                },
            )
            assert response.status_code == 201, response.text
            assert "fixture-protected-api-key" not in response.text
            assert app.state.application.runtime._settings().api_key == "fixture-protected-api-key"
            assert app.state.application.store.model_config("protected")["api_key"] is None
    finally:
        app.state.application.store.close()
