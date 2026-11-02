"""Command metadata recovers atomically with requests, without storing replay input."""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.contracts import RuntimeScope
from orion.contracts.commands import CommandPage, CommandRunInput
from orion.persistence.ownership import RuntimeLease
from orion.persistence.sqlite import SQLiteStore


def pending(store):
    session = store.create_session()
    request = store.create_request(session)
    scope = RuntimeScope(session_id=session, principal_id="local", workspace_id="local")
    values = CommandRunInput(target_ref="a" * 32, shell="cmd", command="private-script-marker")
    record, created = store.create_command(scope, values, request, "once")
    assert created
    store.save_command_observation(
        CommandPage(
            command_id=record["command_id"],
            target_ref=values.target_ref,
            shell="cmd",
            state="running",
        )
    )
    return scope, request, record["command_id"]


def test_restart_recovers_command_unknown_without_replay_or_raw_output(tmp_path):
    database = tmp_path / "orion.db"
    store = SQLiteStore(database)
    scope, request, identity = pending(store)
    store.close()
    backend = ScriptedBackend([])
    application = build_application(database, backend, seed_model_from_environment=False)
    try:
        record = application.store.command_record(scope, identity, "a" * 32)
        assert record["state"] == "outcome_unknown"
        assert json.loads(record["observation_json"])["output_available"] is False
        assert application.store.request(request)["status"] == "failed"
        event = next(
            event
            for event in application.store.events(request)
            if event["type"] == "request.failed"
        )
        assert event["payload"]["outcome_unknown"] is True
        assert "private-script-marker" not in "\n".join(application.store._connection.iterdump())
        assert backend.calls == []
    finally:
        application.store.close()


def test_recovery_event_failure_rolls_command_state_back_together(tmp_path):
    database = tmp_path / "orion.db"
    lease = RuntimeLease(database)
    store = SQLiteStore(database, on_close=lease.close)
    scope, request, identity = pending(store)
    store._connection.execute(
        "CREATE TRIGGER fail_recovery BEFORE INSERT ON request_events "
        "BEGIN SELECT RAISE(ABORT,'injected recovery failure'); END"
    )
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.recover_interrupted_requests(lease)
        assert store.command_record(scope, identity, "a" * 32)["state"] == "running"
        assert store.request(request)["status"] == "queued"
    finally:
        store.close()
