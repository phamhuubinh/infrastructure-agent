"""Native credentials are single-use/hash-only and rotation cannot undo replay revoke."""

import concurrent.futures
import sqlite3
import threading

import pytest
from pydantic import SecretStr

from orion.access import Principal
from orion.access.native import ACCESS_SECONDS, SESSION_SECONDS, NativeAuthError, NativeAuthService
from orion.contracts.native_auth import NativeEnrollmentInput
from orion.knowledge.blob_store import LocalBlobStore
from orion.persistence.backup import export_bundle, import_bundle, validate_bundle
from orion.persistence.sqlite import SQLiteStore

OWNER = Principal("local", "local")


def enroll(service, owner=OWNER):
    code = service.create_enrollment(owner)
    values = NativeEnrollmentInput(
        code=SecretStr(code.code), name="Fixture client", platform="linux"
    )
    return code, values, service.enroll(values)


def test_single_use_hash_only_rotation_and_recognized_replay_revokes_family(store):
    service = NativeAuthService(store)
    code, values, pair = enroll(service)
    assert service.authenticate(pair.access_token) == (OWNER, pair.session_id)
    with pytest.raises(NativeAuthError, match="invalid_enrollment"):
        service.enroll(values)
    rotated = service.refresh(pair.refresh_token)
    assert rotated.session_id == pair.session_id and rotated.refresh_token != pair.refresh_token
    assert service.authenticate(pair.access_token) is None
    assert service.authenticate(rotated.access_token) == (OWNER, pair.session_id)
    with pytest.raises(NativeAuthError, match="invalid_refresh"):
        service.refresh("orion_refresh_" + "x" * 43)
    assert service.authenticate(rotated.access_token)
    with pytest.raises(NativeAuthError, match="refresh_replayed"):
        service.refresh(pair.refresh_token)
    assert service.authenticate(rotated.access_token) is None
    with pytest.raises(NativeAuthError, match="invalid_refresh"):
        service.refresh(rotated.refresh_token)
    dump = "\n".join(store._connection.iterdump())
    for secret in (
        code.code,
        pair.access_token,
        pair.refresh_token,
        rotated.access_token,
        rotated.refresh_token,
    ):
        assert secret not in dump
    assert "access_token" not in repr(pair) and "code=" not in repr(code)


def test_expiry_revoke_owner_isolation_and_restart(store):
    now = [1000.0]
    service = NativeAuthService(store, lambda: now[0])
    _, _, pair = enroll(service)
    other = Principal("other", "workspace")
    assert service.sessions(other) == []
    assert not service.revoke(pair.session_id, other)
    assert NativeAuthService(store, lambda: now[0]).authenticate(pair.access_token)
    now[0] += ACCESS_SECONDS
    assert service.authenticate(pair.access_token) is None
    renewed = service.refresh(pair.refresh_token)
    assert service.authenticate(renewed.access_token)
    assert service.revoke(pair.session_id, OWNER)
    assert service.revoke(pair.session_id, OWNER)
    assert not service.authenticate(renewed.access_token)
    assert service.sessions(OWNER)[0].revoked_at == int(now[0])
    _, _, expiring = enroll(service)
    now[0] += SESSION_SECONDS
    assert not service.authenticate(expiring.access_token)
    with pytest.raises(NativeAuthError, match="invalid_refresh"):
        service.refresh(expiring.refresh_token)


def test_expired_and_excess_enrollment_codes_are_unusable(store):
    now = [1000.0]
    service = NativeAuthService(store, lambda: now[0])
    codes = [service.create_enrollment(OWNER) for _ in range(8)]
    with pytest.raises(NativeAuthError, match="capacity"):
        service.create_enrollment(OWNER)
    now[0] = codes[0].expires_at
    with pytest.raises(NativeAuthError, match="invalid_enrollment"):
        service.enroll(NativeEnrollmentInput(code=codes[0].code, name="client", platform="ios"))
    assert service.create_enrollment(OWNER)


def test_failed_rotation_rolls_back_both_tokens_and_existing_access(store):
    service = NativeAuthService(store)
    _, _, pair = enroll(service)
    with store._connection:
        store._connection.execute(
            "CREATE TRIGGER reject_refresh BEFORE INSERT ON native_refresh_tokens "
            "BEGIN SELECT RAISE(ABORT,'fixture refusal'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="fixture refusal"):
        service.refresh(pair.refresh_token)
    assert service.authenticate(pair.access_token)
    assert store._connection.execute("SELECT used FROM native_refresh_tokens").fetchone()[0] == 0
    with store._connection:
        store._connection.execute("DROP TRIGGER reject_refresh")
    assert service.authenticate(service.refresh(pair.refresh_token).access_token)


def test_separate_connection_cannot_consume_enrollment_twice(tmp_path):
    first = SQLiteStore(tmp_path / "orion.db")
    second = SQLiteStore(tmp_path / "orion.db")
    try:
        service = NativeAuthService(first)
        _, values, pair = enroll(service)
        with pytest.raises(NativeAuthError, match="invalid_enrollment"):
            NativeAuthService(second).enroll(values)
        assert NativeAuthService(second).authenticate(pair.access_token)
    finally:
        first.close()
        second.close()


def test_concurrent_refresh_connections_commit_one_rotation_then_revoke_replay(tmp_path):
    path = tmp_path / "native.db"
    first, second = SQLiteStore(path), SQLiteStore(path)
    barrier = threading.Barrier(2)
    try:
        service = NativeAuthService(first)
        _, _, original = enroll(service)

        def rotate(store):
            barrier.wait(timeout=5)
            try:
                return NativeAuthService(store).refresh(original.refresh_token)
            except NativeAuthError as error:
                return error.category

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(rotate, (first, second)))
        assert (
            sum(isinstance(result, str) and result == "refresh_replayed" for result in results) == 1
        )
        successful = next(result for result in results if not isinstance(result, str))
        assert service.authenticate(successful.access_token) is None
        assert service.sessions(OWNER)[0].revoked_at is not None
    finally:
        first.close()
        second.close()


def test_restart_keeps_credentials_but_managed_restore_revokes_sessions_and_codes(tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    LocalBlobStore(root / "blobs")
    path = root / "orion.db"
    first = SQLiteStore(path)
    service = NativeAuthService(first)
    _, _, pair = enroll(service)
    unused = service.create_enrollment(OWNER)
    first.close()
    restarted = SQLiteStore(path)
    try:
        assert NativeAuthService(restarted).authenticate(pair.access_token)
    finally:
        restarted.close()
    destination = tmp_path / "backups"
    destination.mkdir()
    bundle = export_bundle(path, destination)
    restored = SQLiteStore(import_bundle(bundle, tmp_path / "restored"))
    try:
        service = NativeAuthService(restored)
        assert service.authenticate(pair.access_token) is None
        with pytest.raises(NativeAuthError, match="invalid_refresh"):
            service.refresh(pair.refresh_token)
        with pytest.raises(NativeAuthError, match="invalid_enrollment"):
            service.enroll(NativeEnrollmentInput(code=unused.code, name="restored", platform="ios"))
        assert service.sessions(OWNER)[0].revoked_at is not None
        validate_bundle(bundle)
    finally:
        restored.close()
