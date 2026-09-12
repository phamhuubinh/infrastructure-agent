"""QA identity observation against real temporary SQLite, without external I/O."""

from __future__ import annotations

import sqlite3
import urllib.error

import pytest
from test_qa_runner import qa_runner as qa_runner


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):  # type: ignore[no-untyped-def]
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        pytest.fail("external network is forbidden")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)


@pytest.mark.parametrize("failure", ["timeout", "http_error"])
@pytest.mark.parametrize("delta", ["single", "zero", "ambiguous", "other_session"])
def test_failed_post_binds_only_single_exact_session_delta(
    qa_runner, store, tmp_path, monkeypatch, failure, delta
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "orion.db"
    session = store.create_session()
    other = store.create_session()
    previous = store.create_request(session, "running")
    observation = qa_runner.RequestObservation(session)
    original_error = (
        qa_runner.QARequestTimeout("unchanged timeout")
        if failure == "timeout"
        else urllib.error.HTTPError("http://qa", 502, "unchanged error", None, None)
    )
    created = []
    posts = []

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        assert method == "POST" and path == f"/api/sessions/{session}/messages"
        posts.append(path)
        if delta != "zero":
            created.append(store.create_request(other if delta == "other_session" else session))
        if delta == "ambiguous":
            created.append(store.create_request(session))
        raise original_error

    def timeline(*args):  # type: ignore[no-untyped-def]
        # Recovery precedes even best-effort timeline capture; no contents needed.
        assert observation.request_id == (created[0] if delta == "single" else None)
        raise qa_runner.QARequestTimeout("timeline also unavailable")

    monkeypatch.setattr(qa_runner, "_json_request", request)
    monkeypatch.setattr(qa_runner, "_timeline", timeline)
    with pytest.raises(type(original_error)) as caught:
        qa_runner._send("http://qa", session, "send", observation, database)
    assert caught.value is original_error and len(posts) == 1
    assert store.request(previous)["status"] == "running"
    if delta == "single":
        assert observation.request_identity_source == "qa_database_delta"
        assert observation.request_id == created[0] != previous
        assert observation.request_identity_reason is None
    else:
        assert observation.request_id is None
        assert observation.request_identity_source == "unavailable"
        assert (
            "ambiguous" if delta == "ambiguous" else "no new request"
        ) in observation.request_identity_reason


@pytest.mark.parametrize(
    "observer", ["normal", "different_id", "missing", "before_error", "after_error"]
)
def test_success_response_is_authoritative_despite_observer(
    qa_runner, store, tmp_path, monkeypatch, observer
) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / ("missing.db" if observer == "missing" else "orion.db")
    session = store.create_session()
    observation = qa_runner.RequestObservation(session)
    snapshots = []
    real_snapshot = qa_runner._request_ids_snapshot

    def snapshot(path, sid):  # type: ignore[no-untyped-def]
        snapshots.append((path, sid))
        if (observer == "before_error" and len(snapshots) == 1) or (
            observer == "after_error" and len(snapshots) == 2
        ):
            return None
        return real_snapshot(path, sid)

    def request(*args):  # type: ignore[no-untyped-def]
        request_id = store.create_request(session)
        return {
            "request_id": "authoritative-response" if observer == "different_id" else request_id,
            "assistant_content": "answer",
        }

    monkeypatch.setattr(qa_runner, "_request_ids_snapshot", snapshot)
    monkeypatch.setattr(qa_runner, "_json_request", request)
    returned = qa_runner._send("http://qa", session, "send", observation, database)
    assert observation.assistant_content == "answer"
    assert returned == observation.request_id
    assert returned == (
        "authoritative-response"
        if observer == "different_id"
        else store.request(returned)["request_id"]
    )
    assert observation.request_identity_source == "message_response"
    assert observation.request_identity_reason is None
    assert snapshots == [(database, session), (database, session)]
    if observer == "missing":
        assert not database.exists()


def test_previous_timeout_still_running_cannot_bind_next_send(
    qa_runner, store, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    session = store.create_session()
    observations = []
    created = []
    attempts = 0

    def request(*args):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        if attempts in (1, 3):
            created.append(store.create_request(session, "running"))
        raise qa_runner.QARequestTimeout()

    monkeypatch.setattr(qa_runner, "_json_request", request)
    monkeypatch.setattr(qa_runner, "_timeline", lambda *args: [])
    for _ in range(3):
        observation = qa_runner.RequestObservation(session)
        observations.append(observation)
        with pytest.raises(qa_runner.QARequestTimeout):
            qa_runner._send("http://qa", session, "turn", observation, tmp_path / "orion.db")
    assert [item.request_id for item in observations] == [created[0], None, created[1]]
    assert all(store.request(request_id)["status"] == "running" for request_id in created)
    assert attempts == 3


@pytest.mark.parametrize("failed_snapshot", [1, 2])
def test_observer_read_failure_is_unavailable_not_an_execution_change(
    qa_runner, store, tmp_path, monkeypatch, failed_snapshot
) -> None:  # type: ignore[no-untyped-def]
    session = store.create_session()
    original_connect = sqlite3.connect
    attempts = []

    def connect(database_uri, **kwargs):  # type: ignore[no-untyped-def]
        attempts.append((database_uri, kwargs))
        assert database_uri.endswith("?mode=ro") and kwargs == {"uri": True, "timeout": 0}
        if len(attempts) == failed_snapshot:
            raise sqlite3.OperationalError("sensitive database failure must not be reported")
        return original_connect(database_uri, **kwargs)

    original_error = qa_runner.QARequestTimeout()

    def request(*args):  # type: ignore[no-untyped-def]
        store.create_request(session)
        raise original_error

    monkeypatch.setattr(qa_runner.sqlite3, "connect", connect)
    monkeypatch.setattr(qa_runner, "_json_request", request)
    monkeypatch.setattr(qa_runner, "_timeline", lambda *args: [])
    observation = qa_runner.RequestObservation(session)
    with pytest.raises(qa_runner.QARequestTimeout) as caught:
        qa_runner._send("http://qa", session, "send", observation, tmp_path / "orion.db")
    assert caught.value is original_error
    assert observation.request_id is None and observation.request_identity_source == "unavailable"
    assert observation.request_identity_reason == (
        f"{'before' if failed_snapshot == 1 else 'after'}-send QA database snapshot unavailable"
    )
    assert len(attempts) == 2


def test_snapshot_is_read_only_and_exactly_session_scoped(qa_runner, store, tmp_path) -> None:  # type: ignore[no-untyped-def]
    session = store.create_session()
    other = store.create_session()
    expected = store.create_request(session)
    store.create_request(other)
    database = tmp_path / "orion.db"
    before = {
        path.name: path.read_bytes()
        for path in tmp_path.glob("orion.db*")
        if not path.name.endswith("-shm")
    }
    assert qa_runner._request_ids_snapshot(database, session) == frozenset({expected})
    assert qa_runner._request_ids_snapshot(database, "' OR 1=1 --") == frozenset()
    assert before == {
        path.name: path.read_bytes()
        for path in tmp_path.glob("orion.db*")
        if not path.name.endswith("-shm")
    }
    assert qa_runner._request_ids_snapshot(tmp_path / "nonexistent.db", session) is None
    assert not (tmp_path / "nonexistent.db").exists()


def test_identity_evidence_version_changes_without_timeout_or_schema_bump(qa_runner) -> None:  # type: ignore[no-untyped-def]
    assert qa_runner.RUNNER_VERSION == "14"
    assert qa_runner.MANIFEST_SCHEMA_VERSION == "2"
    assert qa_runner.EXECUTION_PROVENANCE_SCHEMA_VERSION == "1"
    assert qa_runner.QA_REQUEST_TIMEOUT_SECONDS == 90
