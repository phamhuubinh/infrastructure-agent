from __future__ import annotations

import asyncio
import gc
import os
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime

import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.chat.runtime import RequestFailed
from orion.contracts import AssistantMessage, ModelTurn, RuntimeScope
from orion.persistence.ownership import RuntimeLease
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.contracts import TaskInput


def test_restart_finishes_ordinary_queued_and_running_requests_without_model_replay(tmp_path):
    path = tmp_path / "application.db"
    app = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    session = app.store.create_session()
    queued = app.store.create_request(session)
    running = app.store.create_request(session)
    app.store.start_request(running)
    app.store.append_timeline(session, running, "user_message", {"content": "Perform the change"})
    app.store.emit_event(
        running, "tool.started", {"call_id": "unconfirmed", "tool_name": "fixture.change"}
    )
    app.store.close()
    backend = ScriptedBackend([])
    restarted = build_application(path, backend, seed_model_from_environment=False)
    try:
        assert restarted.store.request(queued)["status"] == "failed"
        assert restarted.store.request(running)["status"] == "failed"
        assert not backend.calls
        terminal = [
            event for event in restarted.store.events(running) if event["type"] == "request.failed"
        ]
        assert len(terminal) == 1 and terminal[0]["payload"]["outcome_unknown"] is True
        assert restarted.store.timeline(session)[0].payload["content"] == "Perform the change"
    finally:
        restarted.store.close()
    again = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    try:
        assert sum(event["type"] == "request.failed" for event in again.store.events(running)) == 1
    finally:
        again.store.close()


def test_request_start_is_compare_and_swap_and_terminal_state_cannot_change(store):
    request = store.create_request(store.create_session())
    assert store.start_request(request) is True
    assert store.start_request(request) is False
    assert store.complete_request(request, "completed") is True
    assert store.complete_request(request, "failed", "late error") is False
    assert store.request(request)["status"] == "completed"
    assert store.request(request)["error_message"] is None


def test_second_application_cannot_recover_or_dispatch_against_a_live_runtime(tmp_path):
    path = tmp_path / "application.db"
    first = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    request = first.store.create_request(first.store.create_session())
    first.store.start_request(request)
    second = None
    try:
        with pytest.raises(RuntimeError, match="another Orion runtime"):
            second = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
        assert first.store.request(request)["status"] == "running"
    finally:
        if second is not None:
            second.store.close()
        first.store.close()


def test_completed_requests_survive_recovery_and_metadata_readers_remain_available(tmp_path):
    path = tmp_path / "application.db"
    app = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    request = app.store.create_request(app.store.create_session())
    app.store.complete_request(request, "completed")
    # A metadata connection is not another runtime and must remain usable.
    reader = SQLiteStore(path)
    assert reader.request(request)["status"] == "completed"
    reader.close()
    app.store.close()
    restarted = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    try:
        assert restarted.store.request(request)["status"] == "completed"
        assert restarted.store.events(request) == []
    finally:
        restarted.store.close()


@pytest.mark.anyio
async def test_duplicate_queued_runtime_invocations_never_replay_or_add_terminal_events(tmp_path):
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Once"))])
    app = build_application(tmp_path / "application.db", backend, seed_model_from_environment=False)
    app.store.create_model_config("openai_compatible", "http://fixture.test", "configured", None)
    session = app.store.create_session()
    request = app.runtime.begin(session, "Hello")
    lock = app.runtime._session_locks.setdefault(session, asyncio.Lock())
    await lock.acquire()
    first = asyncio.create_task(app.runtime.run(session, request))
    second = asyncio.create_task(app.runtime.run(session, request))
    await asyncio.sleep(0)
    lock.release()
    try:
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert sum(isinstance(result, RequestFailed) for result in results) == 1
        assert len(backend.calls) == 1
        terminal = [
            event["type"]
            for event in app.store.events(request)
            if event["type"] in {"request.completed", "request.failed", "request.cancelled"}
        ]
        assert terminal == ["request.completed"]
        assert app.store.request(request)["status"] == "completed"
    finally:
        app.store.close()


def test_native_os_lease_survives_other_process_and_releases_after_abrupt_exit(tmp_path):
    path, ready = tmp_path / "application.db", tmp_path / "owned"
    script = (
        "import os,sys; from pathlib import Path; "
        "from orion.persistence.ownership import RuntimeLease; "
        "lease=RuntimeLease(Path(sys.argv[1])); Path(sys.argv[2]).write_text('owned'); "
        "sys.stdin.buffer.read(1); os._exit(0)"
    )
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", script, str(path), str(ready)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            if child.poll() is not None:
                pytest.fail("Isolated runtime lease process failed to start")
            if time.monotonic() >= deadline:
                pytest.fail("Runtime lease process did not become ready")
            time.sleep(0.01)
        with pytest.raises(RuntimeError, match="another Orion runtime"):
            RuntimeLease(path)
        child.communicate(b"x", timeout=10)
        assert child.returncode == 0
        recovered = RuntimeLease(path)
        assert recovered.owns(path)
        recovered.close()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_ownership_file_hardlink_cannot_modify_another_file(tmp_path):
    victim = tmp_path / "victim"
    victim.write_bytes(b"")
    os.link(victim, tmp_path / "application.db.runtime.lock")
    with pytest.raises(RuntimeError, match="ownership file is unavailable"):
        RuntimeLease(tmp_path / "application.db")
    assert victim.read_bytes() == b""


def test_unreferenced_native_lease_does_not_leak_a_kernel_lock(tmp_path):
    path = tmp_path / "application.db"
    lease = RuntimeLease(path)
    assert lease.owns(path)
    del lease
    gc.collect()
    replacement = RuntimeLease(path)
    replacement.close()


def test_recovery_requires_matching_live_runtime_ownership(tmp_path):
    path = tmp_path / "application.db"
    lease = RuntimeLease(path)
    store = SQLiteStore(path, on_close=lease.close)
    request = store.create_request(store.create_session())
    other = RuntimeLease(tmp_path / "different.db")
    try:
        with pytest.raises(RuntimeError, match="exclusive Orion runtime ownership"):
            store.recover_interrupted_requests(other)
        assert store.request(request)["status"] == "queued"
        other.close()
        with pytest.raises(RuntimeError, match="exclusive Orion runtime ownership"):
            store.recover_interrupted_requests(other)
    finally:
        other.close()
        store.close()


def test_recovery_state_notice_event_and_schedule_changes_roll_back_together(tmp_path):
    path = tmp_path / "application.db"
    lease = RuntimeLease(path)
    store = SQLiteStore(path, on_close=lease.close)
    session = store.create_session()
    request = store.create_request(session)
    store.create_pending_authorization(
        request, "call", session, "fixture.change", "target", "a" * 64, {}
    )
    now = datetime.now(UTC)
    scope = RuntimeScope(session_id=session, principal_id="local", workspace_id="local")
    task = store.create_scheduled_task(
        scope, TaskInput(prompt="Read fixture", schedule_kind="once", run_at=now.isoformat()), now
    )
    claim = store.claim_scheduled_run(now)
    scheduled_request = store.create_and_link_scheduled_request(
        claim["run_id"], task["execution_session_id"]
    )
    run_before = store.scheduled_history(scope, task["task_id"], 10)
    store._connection.execute(
        "CREATE TRIGGER reject_recovery BEFORE INSERT ON request_events "
        "BEGIN SELECT RAISE(ABORT, 'fixture recovery failure'); END"
    )
    try:
        with pytest.raises(sqlite3.IntegrityError, match="fixture recovery failure"):
            store.recover_interrupted_requests(lease)
        assert store.request(request)["status"] == "queued"
        assert store.pending_authorization(request, "call")["state"] == "pending"
        assert store.timeline(session) == [] and store.events(request) == []
        assert store.request(scheduled_request)["status"] == "queued"
        assert store.scheduled_history(scope, task["task_id"], 10) == run_before
    finally:
        store.close()


def test_committed_tool_result_before_public_event_does_not_invent_unknown_outcome(tmp_path):
    path = tmp_path / "application.db"
    app = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    session = app.store.create_session()
    request = app.store.create_request(session)
    app.store.start_request(request)
    app.store.emit_event(request, "tool.started", {"call_id": "verified"})
    app.store.append_timeline(
        session,
        request,
        "tool_result",
        {"result": {"status": "success", "call_id": "verified", "data": {"changed": True}}},
        call_id="verified",
        tool_name="fixture.change",
    )
    app.store.close()
    restarted = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    try:
        terminal = next(
            event for event in restarted.store.events(request) if event["type"] == "request.failed"
        )
        assert terminal["payload"]["outcome_unknown"] is False
        assert restarted.store.timeline(session)[0].kind == "tool_result"
    finally:
        restarted.store.close()


def test_failed_composition_releases_native_runtime_lease(tmp_path, monkeypatch):
    path = tmp_path / "application.db"
    original = SQLiteStore._create_schema

    def fail_schema(self):
        raise RuntimeError("fixture schema failure")

    monkeypatch.setattr(SQLiteStore, "_create_schema", fail_schema)
    with pytest.raises(RuntimeError, match="fixture schema failure"):
        build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    monkeypatch.setattr(SQLiteStore, "_create_schema", original)
    app = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    app.store.close()
