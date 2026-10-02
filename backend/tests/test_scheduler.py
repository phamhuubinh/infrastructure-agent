"""Scheduler v1 deterministic persistence, calendar, runtime and lifecycle coverage."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from conftest import ScriptedBackend
from pydantic import ValidationError

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    RuntimeScope,
)
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.contracts import TaskInput
from orion.scheduler.engine import SchedulerEngine
from orion.scheduler.schedules import CronSchedule, parse_instant
from orion.scheduler.service import SchedulerService
from orion.tool_runtime.mutation_authorization import MutationMode

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def scope(store: SQLiteStore, project_id: str | None = None) -> RuntimeScope:
    return RuntimeScope(
        session_id=store.create_session(project_id=project_id),
        principal_id="local",
        workspace_id="local",
        project_id=project_id,
    )


def once(moment: datetime = NOW, prompt: str = "Read current information.") -> TaskInput:
    return TaskInput(prompt=prompt, schedule_kind="once", run_at=moment.isoformat())


def recurring(cron: str = "* * * * *", timezone: str = "UTC") -> TaskInput:
    return TaskInput(
        prompt="Read current information.", schedule_kind="recurring", cron=cron, timezone=timezone
    )


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-01",
        "2026-01-01T00:00:00",
        "2026-01-01 00:00:00+00:00",
        "2026-02-30T00:00:00Z",
        "2026-01-01T00:00:60Z",
        "2026-01-01T00:00:00+24:00",
        "2026-01-01T00:00:00+00:60",
    ],
)
def test_reject_invalid_or_naive_instants(timestamp: str) -> None:
    with pytest.raises(ValueError):
        parse_instant(timestamp)


def test_one_time_canonical_utc_and_closed_bounded_input() -> None:
    task = TaskInput(prompt="read", schedule_kind="once", run_at="2026-01-01T07:00:00+07:00")
    assert task.run_at == NOW.isoformat()
    for extra in ({"timezone": "UTC"}, {"cron": "* * * * *"}, {"principal_id": "other"}):
        with pytest.raises(ValidationError):
            TaskInput.model_validate(
                dict(prompt="read", schedule_kind="once", run_at=NOW.isoformat(), **extra)
            )
    for prompt in (" ", "x" * 16001):
        with pytest.raises(ValidationError):
            once(prompt=prompt)


@pytest.mark.parametrize(
    "cron",
    [
        "* * * * * *",
        "@daily",
        "60 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * * 13 *",
        "* * * * 8",
        "*/0 * * * *",
        "5-1 * * * *",
        "*/x * * * *",
        "1,,2 * * * *",
        "* * * * ?",
    ],
)
def test_cron_validation(cron: str) -> None:
    with pytest.raises(ValueError):
        CronSchedule.parse(cron, "UTC")


def test_timezone_validation_and_impossible_calendar() -> None:
    with pytest.raises(ValueError):
        recurring(timezone="not/a/timezone")
    with pytest.raises(ValueError, match="no occurrence"):
        CronSchedule.parse("0 0 30 FEB *", "UTC").next_after(NOW)


def test_calendar_grammar_and_no_drift() -> None:
    cron = CronSchedule.parse("  0,30  9-17/2 * JAN,MAR MON-FRI  ", "Asia/Bangkok")
    assert cron.text == "0,30 9-17/2 * JAN,MAR MON-FRI"
    first = cron.next_after(NOW)
    assert first == datetime(2026, 1, 1, 2, tzinfo=UTC)
    assert cron.next_after(first) == first + timedelta(minutes=30)
    # Restricted DOM and DOW use ordinary cron OR semantics.
    assert CronSchedule.parse("0 0 2 * SUN", "UTC").next_after(NOW).day == 2
    assert CronSchedule.parse("0 0 * * 7", "UTC").next_after(NOW).day == 4
    leap = CronSchedule.parse("0 0 29 FEB *", "UTC")
    assert leap.next_after(datetime(2097, 1, 1, tzinfo=UTC)).year == 2104


def test_dst_gap_fold_and_local_calendar_days() -> None:
    gap = CronSchedule.parse("30 2 * * *", "America/New_York")
    before = datetime(2026, 3, 7, 7, 30, tzinfo=UTC)
    assert gap.next_after(before) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    fold = CronSchedule.parse("30 1 * * *", "America/New_York")
    first = fold.next_after(datetime(2026, 11, 1, 4, tzinfo=UTC))
    second = fold.next_after(first)
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert second == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert fold.latest_at(second) == second
    daily = CronSchedule.parse("0 12 * * *", "America/New_York")
    first = daily.next_after(datetime(2026, 3, 7, tzinfo=UTC))
    assert daily.next_after(first) - first == timedelta(hours=23)


def test_additive_migration_and_task_restart(tmp_path: Path) -> None:
    path = tmp_path / "orion.db"
    with sqlite3.connect(path) as legacy:
        legacy.execute(
            "CREATE TABLE sessions(session_id TEXT PRIMARY KEY, created_at TEXT NOT NULL)"
        )
        legacy.execute("INSERT INTO sessions VALUES ('existing', '2020-01-01')")
    store = SQLiteStore(path)
    owner = scope(store)
    task = store.create_scheduled_task(owner, recurring(timezone="Asia/Bangkok"), NOW)
    single = store.create_scheduled_task(owner, once(), NOW)
    store.close()
    store = SQLiteStore(path)
    assert store.session_exists("existing")
    assert store.scheduled_task(owner, task["task_id"]) == task
    assert store.scheduled_task(owner, single["task_id"]) == single
    assert store.session_identity(task["execution_session_id"])["principal_id"] == "local"
    store.close()


def test_scope_binding_no_attachment_copy_and_isolation(store: SQLiteStore) -> None:
    project = store.create_project("project")["project_id"]
    owner = scope(store, project)
    task = store.create_scheduled_task(owner, once(), NOW)
    identity = store.session_identity(task["execution_session_id"])
    assert identity["project_id"] == project
    assert store.session_attachment_ids(task["execution_session_id"]) == ()
    for changes in ({"principal_id": "other"}, {"workspace_id": "other"}, {"project_id": None}):
        foreign = owner.model_copy(update=changes)
        for operation in (
            lambda foreign=foreign: store.scheduled_task(foreign, task["task_id"]),
            lambda foreign=foreign: store.scheduled_history(foreign, task["task_id"], 10),
            lambda foreign=foreign: store.change_scheduled_task(
                foreign, task["task_id"], "delete", NOW
            ),
            lambda foreign=foreign: store.create_scheduled_task(foreign, once(), NOW),
        ):
            with pytest.raises(KeyError):
                operation()
        assert store.scheduled_tasks(foreign, 10) == []


def test_atomic_claim_coalesces_and_advances_before_execution(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, recurring(), NOW)
    later = NOW + timedelta(days=365, seconds=17)
    claim = store.claim_scheduled_run(later)
    assert claim["task_id"] == task["task_id"]
    assert claim["scheduled_for"] == later.replace(second=0).isoformat()
    saved = store.scheduled_task(owner, task["task_id"])
    assert saved["next_run_at"] == (later.replace(second=0) + timedelta(minutes=1)).isoformat()
    assert store.scheduled_history(owner, task["task_id"], 10)[0]["status"] == "running"
    assert store.claim_scheduled_run(later + timedelta(minutes=10)) is None
    for action in ("pause", "resume", "delete"):
        with pytest.raises(RuntimeError, match="active_run"):
            store.change_scheduled_task(owner, task["task_id"], action, later)
    store.finish_scheduled_run(claim["run_id"], "failed", later + timedelta(seconds=45))
    assert store.scheduled_task(owner, task["task_id"])["next_run_at"] == saved["next_run_at"]
    assert store.claim_scheduled_run(later + timedelta(minutes=1)) is not None


def test_atomic_duplicate_claim_across_store_connections(tmp_path: Path) -> None:
    path = tmp_path / "orion.db"
    first, second = SQLiteStore(path), SQLiteStore(path)
    owner = scope(first)
    task = first.create_scheduled_task(owner, once(), NOW)
    boundary = Barrier(2)

    def claim_at_once(store: SQLiteStore):  # type: ignore[no-untyped-def]
        boundary.wait(timeout=5)
        return store.claim_scheduled_run(NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim_at_once, (first, second)))
    assert sum(claim is not None for claim in claims) == 1
    claim = next(claim for claim in claims if claim is not None)
    assert second.claim_scheduled_run(NOW) is None
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO scheduled_runs(run_id, task_id, scheduled_for, status, started_at) "
            "VALUES ('duplicate', ?, ?, 'completed', ?)",
            (task["task_id"], claim["scheduled_for"], NOW.isoformat()),
        )
    first.close()
    second.close()


def test_claim_transaction_rolls_back_on_advance_failure(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    store._connection.execute(  # noqa: SLF001 - deliberate transactional fault injection.
        "CREATE TRIGGER reject_advance BEFORE UPDATE ON scheduled_tasks "
        "BEGIN SELECT RAISE(ABORT, 'advance failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.claim_scheduled_run(NOW)
    assert store.scheduled_history(owner, task["task_id"], 50) == []
    assert store.scheduled_task(owner, task["task_id"])["next_run_at"] == NOW.isoformat()


def test_crash_recovery_no_retry_and_recurring_continues(tmp_path: Path) -> None:
    path = tmp_path / "orion.db"
    store = SQLiteStore(path)
    owner = scope(store)
    single = store.create_scheduled_task(owner, once(), NOW)
    repeated = store.create_scheduled_task(owner, recurring(), NOW)
    assert store.claim_scheduled_run(NOW)["task_id"] == single["task_id"]
    assert store.claim_scheduled_run(NOW + timedelta(minutes=1))["task_id"] == repeated["task_id"]
    ordinary_request = store.create_request(owner.session_id)
    store.start_request(ordinary_request)
    store.close()
    store = SQLiteStore(path)
    store.reconcile_scheduled_runs(NOW + timedelta(minutes=1))
    assert store.request(ordinary_request)["status"] == "running"
    for task in (single, repeated):
        assert store.scheduled_history(owner, task["task_id"], 10)[0]["status"] == "interrupted"
    assert store.claim_scheduled_run(NOW + timedelta(minutes=1)) is None
    next_claim = store.claim_scheduled_run(NOW + timedelta(minutes=2))
    assert next_claim["task_id"] == repeated["task_id"]
    assert store.scheduled_history(owner, single["task_id"], 10)[0]["status"] == "interrupted"
    store.close()


@pytest.mark.parametrize(
    "ownership", ["ordinary", "active", "wrong_session", "completed", "failed", "interrupted"]
)
def test_begin_scheduled_requires_active_scheduler_ownership(
    tmp_path: Path, ownership: str
) -> None:
    app = build_application(tmp_path / "orion.db", ScriptedBackend([]))
    store = app.store
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    session_id = task["execution_session_id"]
    if ownership == "ordinary":
        # Even in the dedicated session, an unlinked request is ordinary Chat work.
        request_id = store.create_request(session_id)
    else:
        request_id = store.create_and_link_scheduled_request(claim["run_id"], session_id)
    if ownership == "wrong_session":
        session_id = owner.session_id
    elif ownership in {"completed", "failed", "interrupted"}:
        # Keep the request queued to isolate the run-ownership guard.
        store.finish_scheduled_run(claim["run_id"], ownership, NOW)
    request_before = store.request(request_id)
    assert request_before["status"] == "queued"
    assert store.is_active_scheduled_request(request_id, session_id) is (ownership == "active")
    if ownership == "active":
        assert app.runtime.begin_scheduled(session_id, task["prompt"], request_id) == request_id
        assert app.runtime._pending_content[request_id] == task["prompt"]
        assert request_id in app.runtime._cancellations
        assert request_id in app.runtime._queued_at
        assert request_id in app.runtime._scheduled_requests
    else:
        with pytest.raises(ValueError, match="Scheduled request is unavailable"):
            app.runtime.begin_scheduled(session_id, task["prompt"], request_id)
        assert not app.runtime._pending_content
        assert not app.runtime._cancellations
        assert not app.runtime._queued_at
        assert not app.runtime._scheduled_requests
    assert store.request(request_id) == request_before
    store.close()


@pytest.mark.parametrize("boundary", ["linked", "adopted", "running"])
@pytest.mark.parametrize("deletion", ["session", "project"])
def test_scheduler_owned_request_crash_recovery(
    tmp_path: Path, boundary: str, deletion: str
) -> None:
    path = tmp_path / "orion.db"
    app = build_application(path, ScriptedBackend([]))
    store = app.store
    project = store.create_project("Project")["project_id"]
    owner = scope(store, project)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    request_id = store.create_and_link_scheduled_request(
        claim["run_id"], task["execution_session_id"]
    )
    if boundary != "linked":
        assert (
            app.runtime.begin_scheduled(task["execution_session_id"], task["prompt"], request_id)
            == request_id
        )
    if boundary == "running":
        store.start_request(request_id)
    assert store.scheduled_history(owner, task["task_id"], 10)[0]["request_id"] == request_id
    assert store._connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 1
    ordinary = scope(store)
    ordinary_queued = store.create_request(ordinary.session_id)
    ordinary_running = store.create_request(ordinary.session_id)
    store.start_request(ordinary_running)
    ordinary_before = [store.request(ordinary_queued), store.request(ordinary_running)]
    with pytest.raises(RuntimeError, match="active_request"):
        store.delete_session(task["execution_session_id"])
    with pytest.raises(RuntimeError, match="active_request"):
        store.delete_project(project)
    store.close()

    # A fresh composition root has neither the pending prompt nor its cancellation state.
    restarted = build_application(path, ScriptedBackend([]))
    store = restarted.store
    assert not restarted.runtime._pending_content
    recovered_at = NOW + timedelta(minutes=1)
    store.reconcile_scheduled_runs(recovered_at)
    run = store.scheduled_history(owner, task["task_id"], 10)[0]
    assert run["status"] == "interrupted"
    assert run["error_kind"] == "process_interrupted"
    assert run["completed_at"] == recovered_at.isoformat()
    request = store.request(request_id)
    assert request["status"] == "failed"
    assert request["error_message"] == "Scheduled execution interrupted."
    assert request["completed_at"] == recovered_at.isoformat()
    assert store.timeline(task["execution_session_id"]) == []
    assert store.claim_scheduled_run(recovered_at + timedelta(days=1)) is None
    assert [store.request(ordinary_queued), store.request(ordinary_running)] == ordinary_before
    store.reconcile_scheduled_runs(recovered_at + timedelta(minutes=1))
    assert store.request(request_id) == request
    assert store.scheduled_history(owner, task["task_id"], 10)[0] == run
    if deletion == "session":
        assert store.delete_session(task["execution_session_id"]) == ()
    else:
        assert store.delete_project(project) == ()
    assert not store.session_exists(task["execution_session_id"])
    assert [store.request(ordinary_queued), store.request(ordinary_running)] == ordinary_before
    store.close()


def test_create_and_link_rolls_back_on_link_failure(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    store._connection.execute(
        "CREATE TRIGGER reject_request_link BEFORE UPDATE OF request_id ON scheduled_runs "
        "BEGIN SELECT RAISE(ABORT, 'link failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="link failed"):
        store.create_and_link_scheduled_request(claim["run_id"], task["execution_session_id"])
    assert store._connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0
    assert store.scheduled_history(owner, task["task_id"], 10)[0]["request_id"] is None


@pytest.mark.parametrize("conflict", ["missing", "terminal", "wrong_session", "already_linked"])
def test_create_and_link_rejects_conflicts_without_orphan_requests(
    store: SQLiteStore, conflict: str
) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    run_id, session_id = claim["run_id"], task["execution_session_id"]
    if conflict == "missing":
        run_id = "missing"
    elif conflict == "terminal":
        store.finish_scheduled_run(run_id, "interrupted", NOW)
    elif conflict == "wrong_session":
        session_id = owner.session_id
    else:
        store.create_and_link_scheduled_request(run_id, session_id)
    before = store.scheduled_history(owner, task["task_id"], 10)
    count = store._connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    with pytest.raises(RuntimeError, match="scheduled_request_conflict"):
        store.create_and_link_scheduled_request(run_id, session_id)
    assert store._connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == count
    assert store.scheduled_history(owner, task["task_id"], 10) == before


@pytest.mark.parametrize("status", ["completed", "incomplete", "failed", "cancelled"])
def test_reconcile_preserves_terminal_scheduler_requests(store: SQLiteStore, status: str) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    request_id = store.create_and_link_scheduled_request(
        claim["run_id"], task["execution_session_id"]
    )
    store.complete_request(request_id, status, "Existing terminal outcome.")
    before = store.request(request_id)
    store.reconcile_scheduled_runs(NOW)
    assert store.request(request_id) == before
    assert store.scheduled_history(owner, task["task_id"], 10)[0]["status"] == "interrupted"


def test_reconcile_request_and_run_changes_roll_back_together(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    request_id = store.create_and_link_scheduled_request(
        claim["run_id"], task["execution_session_id"]
    )
    request_before = store.request(request_id)
    run_before = store.scheduled_history(owner, task["task_id"], 10)
    store._connection.execute(
        "CREATE TRIGGER reject_interruption BEFORE UPDATE OF status ON scheduled_runs "
        "BEGIN SELECT RAISE(ABORT, 'interruption failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="interruption failed"):
        store.reconcile_scheduled_runs(NOW)
    assert store.request(request_id) == request_before
    assert store.scheduled_history(owner, task["task_id"], 10) == run_before


def test_pause_resume_delete_and_bounded_history(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, recurring(), NOW)
    store.change_scheduled_task(owner, task["task_id"], "pause", NOW)
    assert store.claim_scheduled_run(NOW + timedelta(days=1)) is None
    store.change_scheduled_task(owner, task["task_id"], "resume", NOW)
    for index in range(1, 105):
        moment = NOW + timedelta(minutes=index)
        claim = store.claim_scheduled_run(moment)
        store.finish_scheduled_run(claim["run_id"], "completed", moment)
    assert len(store.scheduled_history(owner, task["task_id"], 1000)) == 100
    assert len(store.scheduled_history(owner, task["task_id"], 3)) == 3
    store.change_scheduled_task(owner, task["task_id"], "delete", NOW)
    assert store.scheduled_tasks(owner, 50) == []
    with pytest.raises(KeyError):
        store.scheduled_task(owner, task["task_id"])
    assert store.claim_scheduled_run(NOW + timedelta(days=1)) is None


def test_one_time_late_once_and_exhaustion(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW + timedelta(days=1))
    assert claim["scheduled_for"] == NOW.isoformat()
    store.finish_scheduled_run(claim["run_id"], "completed", NOW + timedelta(days=1))
    assert store.claim_scheduled_run(NOW + timedelta(days=2)) is None
    assert store.scheduled_task(owner, task["task_id"])["state"] == "completed"
    with pytest.raises(RuntimeError, match="exhausted"):
        store.change_scheduled_task(owner, task["task_id"], "resume", NOW)


def test_invalid_session_integrity_pauses_before_claim(store: SQLiteStore) -> None:
    owner = scope(store)
    task = store.create_scheduled_task(owner, once(), NOW)
    with store._connection:  # noqa: SLF001 - simulate corrupted persisted ownership.
        store._connection.execute(  # noqa: SLF001
            "UPDATE sessions SET workspace_id = 'other' WHERE session_id = ?",
            (task["execution_session_id"],),
        )
    store.reconcile_scheduled_runs(NOW)
    assert store.scheduled_task(owner, task["task_id"])["state"] == "paused"
    assert store.claim_scheduled_run(NOW) is None


def test_session_project_deletion_claim_conflict_and_cleanup(store: SQLiteStore) -> None:
    project = store.create_project("Project")["project_id"]
    owner = scope(store, project)
    task = store.create_scheduled_task(owner, once(), NOW)
    claim = store.claim_scheduled_run(NOW)
    with pytest.raises(RuntimeError, match="active_request"):
        store.delete_session(task["execution_session_id"])
    with pytest.raises(RuntimeError, match="active_request"):
        store.delete_project(project)
    store.finish_scheduled_run(claim["run_id"], "completed", NOW)
    assert store.delete_project(project) == ()
    assert store.scheduled_tasks(owner, 50) == []


@pytest.mark.anyio
@pytest.mark.parametrize("mode", [MutationMode.AUTO, MutationMode.CONFIRM])
async def test_same_runtime_registry_project_reads_and_forced_read_only(
    tmp_path: Path, mode
) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "2+2"},
                    ),
                    ModelToolCall(
                        call_id="mutate",
                        tool_name="scheduler.create",
                        arguments={
                            "prompt": "mutation",
                            "schedule_kind": "once",
                            "run_at": NOW.isoformat(),
                        },
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="project-read", tool_name="knowledge.list_documents", arguments={}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Read succeeded; mutation blocked.")),
        ]
    )
    app = build_application(tmp_path / "orion.db", backend)
    app.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    app.scheduler.clock = app.scheduler_engine.clock = lambda: NOW
    project = app.store.create_project("Knowledge", instructions="Use project knowledge.")[
        "project_id"
    ]
    owner = scope(app.store, project)
    attachment = app.knowledge.attach(owner.session_id, "session.txt", b"Ordinary session secret")
    app.knowledge.attach_project(project, "project.txt", b"Project knowledge")
    task = app.scheduler.create(owner, once())
    app.store.set_session_mutation_mode(task["execution_session_id"], mode)
    assert await asyncio.wait_for(app.scheduler_engine.tick(), timeout=5)
    history = app.scheduler.history(owner, task["task_id"])
    assert history[0]["status"] == "completed"
    assert history[0]["request_id"]
    assert not await app.scheduler_engine.tick()
    timeline = app.store.timeline(task["execution_session_id"])
    results = [item.payload["result"] for item in timeline if item.kind == "tool_result"]
    assert any((result.get("data") or {}).get("value") == 4 for result in results)
    blocked = next(
        result["error"]
        for result in results
        if (result.get("error") or {}).get("code") == "operation_blocked"
    )
    assert blocked["message"].startswith("Scheduled executions are read-only.")
    assert len(app.scheduler.list_tasks(owner)) == 1
    assert not any(
        event["type"] == "tool.authorization_required"
        for event in app.store.events(history[0]["request_id"])
    )
    context, tools = backend.calls[0]
    assert {tool.name for tool in tools} == {tool.name for tool in app.registry.definitions()}
    context_text = " ".join(message.content for message in context)
    assert "Use project knowledge." in context_text
    assert attachment.attachment_id not in context_text
    assert app.store.session_attachment_ids(task["execution_session_id"]) == ()
    assert app.runtime._registry is app.registry  # noqa: SLF001
    app.store.close()


@pytest.mark.anyio
async def test_adoption_failure_terminalizes_linked_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = build_application(tmp_path / "orion.db", ScriptedBackend([]))
    app.scheduler.clock = app.scheduler_engine.clock = lambda: NOW
    owner = scope(app.store)
    task = app.scheduler.create(owner, once())

    def reject_adoption(session_id: str, content: str, request_id: str) -> str:
        assert app.store.request(request_id)["status"] == "queued"
        raise RuntimeError("Sensitive provider detail must not be persisted.")

    monkeypatch.setattr(app.runtime, "begin_scheduled", reject_adoption)
    assert await app.scheduler_engine.tick()
    run = app.scheduler.history(owner, task["task_id"])[0]
    assert run["status"] == "failed"
    request = app.store.request(run["request_id"])
    assert request["status"] == "failed"
    assert request["error_message"] == "Scheduled execution failed."
    assert app.store.delete_session(task["execution_session_id"]) == ()
    app.store.close()


@pytest.mark.anyio
async def test_runtime_failure_bounded_redacted_and_next_run_eligible(tmp_path: Path) -> None:
    app = build_application(tmp_path / "orion.db", ScriptedBackend([]))
    moment = [NOW]
    app.scheduler.clock = app.scheduler_engine.clock = lambda: moment[0]
    owner = scope(app.store)
    task = app.scheduler.create(owner, recurring())
    moment[0] += timedelta(minutes=1)
    assert await app.scheduler_engine.tick()
    run = app.scheduler.history(owner, task["task_id"])[0]
    assert run["status"] == "failed"
    assert run["error_kind"] == "runtime_failed"
    assert run["error_message"] == "Scheduled execution failed."
    assert app.scheduler.get(owner, task["task_id"])["state"] == "enabled"
    moment[0] += timedelta(minutes=1)
    assert await app.scheduler_engine.tick()
    assert len(app.scheduler.history(owner, task["task_id"])) == 2
    app.store.close()


@pytest.mark.anyio
async def test_wake_idle_start_once_stop_and_single_concurrency(store: SQLiteStore) -> None:
    class Runtime:
        calls = 0
        active = 0
        max_active = 0
        entered = asyncio.Event()
        release = asyncio.Event()

        def begin_scheduled(self, session_id: str, prompt: str, request_id: str) -> str:
            self.calls += 1
            assert store.request(request_id)["session_id"] == session_id
            return request_id

        async def run(self, session_id: str, request_id: str):  # type: ignore[no-untyped-def]
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.entered.set()
            await self.release.wait()
            self.active -= 1
            store.complete_request(request_id, "completed")
            from orion.chat.runtime import RequestOutcome

            return RequestOutcome(request_id, "done")

        def cancel(self, request_id: str) -> None:
            self.release.set()

    fake = Runtime()
    service = SchedulerService(store, lambda: NOW)
    delays = []
    sleeping = asyncio.Event()

    async def wait(event: asyncio.Event, delay: float | None) -> None:
        delays.append(delay)
        sleeping.set()
        await event.wait()

    engine = SchedulerEngine(store, fake, service, lambda: NOW, wait)  # type: ignore[arg-type]
    engine.start()
    worker = engine._worker  # noqa: SLF001
    engine.start()
    assert worker is engine._worker  # noqa: SLF001
    await sleeping.wait()
    assert delays == [None]
    owner = scope(store)
    tasks = [service.create(owner, once()), service.create(owner, once())]
    await fake.entered.wait()
    task = next(task for task in tasks if service.history(owner, task["task_id"]))
    concurrent = asyncio.create_task(engine.tick())
    await asyncio.sleep(0)
    assert fake.calls == 1
    with pytest.raises(RuntimeError):
        service.change(owner, task["task_id"], "pause")
    await engine.stop()
    await concurrent
    assert fake.max_active == 1
    assert worker.done()


@pytest.mark.anyio
async def test_next_due_sleep_and_resume_wake(store: SQLiteStore) -> None:
    service = SchedulerService(store, lambda: NOW)
    owner = scope(store)
    task = service.create(owner, once(NOW + timedelta(hours=1)))
    service.change(owner, task["task_id"], "pause")
    delays = []
    sleeping = asyncio.Queue()

    async def wait(event: asyncio.Event, delay: float | None) -> None:
        delays.append(delay)
        await sleeping.put(None)
        await event.wait()

    engine = SchedulerEngine(store, None, service, lambda: NOW, wait)  # type: ignore[arg-type]
    engine.start()
    await sleeping.get()
    assert delays == [None]
    service.change(owner, task["task_id"], "resume")
    await sleeping.get()
    assert delays == [None, 3600.0]
    await engine.stop()


@pytest.mark.anyio
async def test_application_lifespan_reconciles_and_stops(tmp_path: Path) -> None:
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    assembled = app.state.application
    assembled.scheduler.clock = assembled.scheduler_engine.clock = lambda: NOW
    owner = scope(assembled.store)
    task = assembled.scheduler.create(owner, once())
    assembled.store.claim_scheduled_run(NOW)
    async with app.router.lifespan_context(app):
        assert assembled.scheduler.history(owner, task["task_id"])[0]["status"] == "interrupted"
        worker = assembled.scheduler_engine._worker  # noqa: SLF001
        assert worker is not None
    assert worker.done()
    assert assembled.scheduler_engine._worker is None  # noqa: SLF001
    assembled.store.close()


@pytest.mark.anyio
async def test_clean_shutdown_interrupts_the_real_runtime_run(tmp_path: Path) -> None:
    from orion.contracts import ModelTurnCompleted
    from orion.models.backend import ModelBackend

    class WaitingBackend(ModelBackend):
        entered = asyncio.Event()

        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            self.entered.set()
            await cancellation.wait()
            yield ModelTurnCompleted(
                turn=ModelTurn(assistant=AssistantMessage(content="cancelled"))
            )

    backend = WaitingBackend()
    app = build_application(tmp_path / "orion.db", backend)
    app.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    app.scheduler.clock = app.scheduler_engine.clock = lambda: NOW
    owner = scope(app.store)
    task = app.scheduler.create(owner, once())
    app.scheduler_engine.start()
    await asyncio.wait_for(backend.entered.wait(), timeout=5)
    await app.scheduler_engine.stop()
    run = app.scheduler.history(owner, task["task_id"])[0]
    assert run["status"] == "interrupted"
    assert app.store.request(run["request_id"])["status"] == "cancelled"
    assert not await app.scheduler_engine.tick()
    app.store.close()
