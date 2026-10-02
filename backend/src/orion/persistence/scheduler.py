"""Additive scheduler tables and atomic claims on the canonical SQLite store."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from orion.contracts import RuntimeScope
from orion.scheduler.contracts import MAX_RESULTS, TaskInput
from orion.scheduler.schedules import CronSchedule, utc_text


class SchedulerPersistence:
    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _create_scheduler_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    task_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT REFERENCES projects(project_id),
                    execution_session_id TEXT NOT NULL UNIQUE
                        REFERENCES sessions(session_id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL CHECK (length(prompt) BETWEEN 1 AND 16000),
                    schedule_kind TEXT NOT NULL CHECK (schedule_kind IN ('once', 'recurring')),
                    run_at TEXT,
                    cron TEXT,
                    timezone TEXT,
                    next_run_at TEXT,
                    state TEXT NOT NULL CHECK
                        (state IN ('enabled', 'paused', 'completed', 'deleted')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    CHECK ((schedule_kind = 'once' AND run_at IS NOT NULL
                        AND cron IS NULL AND timezone IS NULL) OR
                        (schedule_kind = 'recurring' AND run_at IS NULL
                        AND cron IS NOT NULL AND timezone IS NOT NULL))
                );
                CREATE INDEX IF NOT EXISTS scheduled_tasks_due
                    ON scheduled_tasks(state, next_run_at);
                CREATE INDEX IF NOT EXISTS scheduled_tasks_owner
                    ON scheduled_tasks(principal_id, workspace_id, project_id, created_at);
                CREATE TABLE IF NOT EXISTS scheduled_runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES scheduled_tasks(task_id) ON DELETE CASCADE,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL CHECK
                        (status IN ('running', 'completed', 'failed', 'interrupted')),
                    request_id TEXT REFERENCES requests(request_id) ON DELETE SET NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_kind TEXT CHECK (length(error_kind) <= 64),
                    error_message TEXT CHECK (length(error_message) <= 512),
                    UNIQUE(task_id, scheduled_for)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS scheduled_runs_one_active
                    ON scheduled_runs(task_id) WHERE status = 'running';
                CREATE INDEX IF NOT EXISTS scheduled_runs_history
                    ON scheduled_runs(task_id, scheduled_for DESC);
            """)

    @staticmethod
    def _scheduler_owner(scope: RuntimeScope) -> tuple[str, str, str | None]:
        return scope.principal_id, scope.workspace_id, scope.project_id

    def create_scheduled_task(
        self, scope: RuntimeScope, task: TaskInput, now: datetime
    ) -> dict[str, Any]:
        next_run = (
            task.run_at
            if task.schedule_kind == "once"
            else utc_text(CronSchedule.parse(task.cron or "", task.timezone or "").next_after(now))
        )
        task_id, session_id, timestamp = str(uuid.uuid4()), str(uuid.uuid4()), utc_text(now)
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            identity = self._connection.execute(
                "SELECT principal_id, workspace_id, project_id, endpoint_id FROM sessions "
                "WHERE session_id = ?",
                (scope.session_id,),
            ).fetchone()
            if identity is None or tuple(identity) != (
                *self._scheduler_owner(scope),
                scope.endpoint_id,
            ):
                raise KeyError("scope")
            if (
                scope.project_id is not None
                and self._connection.execute(
                    "SELECT 1 FROM projects WHERE project_id = ? AND deleted_at IS NULL",
                    (scope.project_id,),
                ).fetchone()
                is None
            ):
                raise KeyError("scope")
            self._connection.execute(
                "INSERT INTO sessions(session_id, principal_id, workspace_id, project_id, "
                "created_at, surface_kind, endpoint_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    *self._scheduler_owner(scope),
                    timestamp,
                    "device_task"
                    if scope.endpoint_id
                    else "project"
                    if scope.project_id
                    else "chat",
                    scope.endpoint_id,
                ),
            )
            self._connection.execute(
                "INSERT INTO scheduled_tasks(task_id, principal_id, workspace_id, project_id, "
                "execution_session_id, prompt, schedule_kind, run_at, cron, timezone, "
                "next_run_at, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'enabled', ?, ?)",
                (
                    task_id,
                    *self._scheduler_owner(scope),
                    session_id,
                    task.prompt,
                    task.schedule_kind,
                    task.run_at,
                    task.cron,
                    task.timezone,
                    next_run,
                    timestamp,
                    timestamp,
                ),
            )
        return self.scheduled_task(scope, task_id)

    def scheduled_task(self, scope: RuntimeScope, task_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM scheduled_tasks WHERE task_id = ? AND principal_id = ? "
                "AND workspace_id = ? AND project_id IS ? AND deleted_at IS NULL",
                (task_id, *self._scheduler_owner(scope)),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)

    def scheduled_tasks(self, scope: RuntimeScope, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM scheduled_tasks WHERE principal_id = ? AND workspace_id = ? "
                "AND project_id IS ? AND deleted_at IS NULL ORDER BY created_at DESC, task_id "
                "LIMIT ?",
                (*self._scheduler_owner(scope), min(MAX_RESULTS, max(1, limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def scheduled_history(
        self, scope: RuntimeScope, task_id: str, limit: int
    ) -> list[dict[str, Any]]:
        with self._lock:
            self.scheduled_task(scope, task_id)
            rows = self._connection.execute(
                "SELECT * FROM scheduled_runs WHERE task_id = ? "
                "ORDER BY scheduled_for DESC, run_id LIMIT ?",
                (task_id, min(MAX_RESULTS, max(1, limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def change_scheduled_task(
        self, scope: RuntimeScope, task_id: str, action: str, now: datetime
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            task = self.scheduled_task(scope, task_id)
            if (
                self._connection.execute(
                    "SELECT 1 FROM scheduled_runs WHERE task_id = ? AND status = 'running'",
                    (task_id,),
                ).fetchone()
                is not None
            ):
                raise RuntimeError("active_run")
            if action != "delete" and task["state"] == "completed":
                raise RuntimeError("exhausted_schedule")
            state = {"pause": "paused", "resume": "enabled", "delete": "deleted"}[action]
            timestamp = utc_text(now)
            # Resume preserves next_run_at: overdue work follows the same coalescing contract.
            self._connection.execute(
                "UPDATE scheduled_tasks SET state = ?, updated_at = ?, deleted_at = ? "
                "WHERE task_id = ?",
                (state, timestamp, timestamp if action == "delete" else None, task_id),
            )
            task.update(
                state=state,
                updated_at=timestamp,
                deleted_at=timestamp if action == "delete" else None,
            )
            return task

    def reconcile_scheduled_runs(self, now: datetime) -> None:
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "UPDATE requests SET status = 'failed', completed_at = ?, "
                "error_message = 'Scheduled execution interrupted.' "
                "WHERE status IN ('queued', 'running') AND request_id IN "
                "(SELECT request_id FROM scheduled_runs WHERE status = 'running')",
                (utc_text(now),),
            )
            self._connection.execute(
                "UPDATE scheduled_runs SET status = 'interrupted', completed_at = ?, "
                "error_kind = 'process_interrupted', error_message = 'Execution interrupted.' "
                "WHERE status = 'running'",
                (utc_text(now),),
            )
            self._pause_invalid_scheduled_tasks(now)

    def _pause_invalid_scheduled_tasks(self, now: datetime) -> None:
        self._connection.execute(
            "UPDATE scheduled_tasks SET state = 'paused', updated_at = ? "
            "WHERE state = 'enabled' AND NOT EXISTS (SELECT 1 FROM sessions s "
            "WHERE s.session_id = scheduled_tasks.execution_session_id "
            "AND s.principal_id = scheduled_tasks.principal_id "
            "AND s.workspace_id = scheduled_tasks.workspace_id "
            "AND s.project_id IS scheduled_tasks.project_id "
            "AND (s.project_id IS NULL OR EXISTS (SELECT 1 FROM projects p "
            "WHERE p.project_id = s.project_id AND p.deleted_at IS NULL)))",
            (utc_text(now),),
        )

    def claim_scheduled_run(self, now: datetime) -> dict[str, Any] | None:
        """Reserve + advance under a SQLite write lock, committed before execution."""
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._pause_invalid_scheduled_tasks(now)
            row = self._connection.execute(
                "SELECT * FROM scheduled_tasks t WHERE state = 'enabled' "
                "AND next_run_at <= ? AND NOT EXISTS (SELECT 1 FROM scheduled_runs r "
                "WHERE r.task_id = t.task_id AND r.status = 'running') "
                "ORDER BY next_run_at, task_id LIMIT 1",
                (utc_text(now),),
            ).fetchone()
            if row is None:
                return None
            task = dict(row)
            scheduled_for = str(task["next_run_at"])
            next_run = None
            if task["schedule_kind"] == "recurring":
                schedule = CronSchedule.parse(task["cron"], task["timezone"])
                scheduled_for = utc_text(schedule.latest_at(now))
                next_run = utc_text(schedule.next_after(datetime.fromisoformat(scheduled_for)))
            run_id = str(uuid.uuid4())
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO scheduled_runs "
                "(run_id, task_id, scheduled_for, status, started_at) "
                "VALUES (?, ?, ?, 'running', ?)",
                (run_id, task["task_id"], scheduled_for, utc_text(now)),
            )
            self._connection.execute(
                "UPDATE scheduled_tasks SET next_run_at = ?, state = ?, updated_at = ? "
                "WHERE task_id = ?",
                (
                    next_run,
                    "completed" if next_run is None else "enabled",
                    utc_text(now),
                    task["task_id"],
                ),
            )
            if not cursor.rowcount:
                return None
            task.update(run_id=run_id, scheduled_for=scheduled_for)
            return task

    def next_scheduled_due(self) -> datetime | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT MIN(next_run_at) FROM scheduled_tasks WHERE state = 'enabled' "
                "AND NOT EXISTS (SELECT 1 FROM scheduled_runs r "
                "WHERE r.task_id = scheduled_tasks.task_id AND r.status = 'running')"
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def create_and_link_scheduled_request(self, run_id: str, execution_session_id: str) -> str:
        """Persist a queued request and its sole scheduler owner in one transaction."""
        request_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "INSERT INTO requests(request_id, session_id, status, created_at) "
                "VALUES (?, ?, 'queued', ?)",
                (request_id, execution_session_id, utc_text(datetime.now(UTC))),
            )
            cursor = self._connection.execute(
                "UPDATE scheduled_runs SET request_id = ? WHERE run_id = ? "
                "AND status = 'running' AND request_id IS NULL AND EXISTS "
                "(SELECT 1 FROM scheduled_tasks t WHERE t.task_id = scheduled_runs.task_id "
                "AND t.execution_session_id = ?)",
                (request_id, run_id, execution_session_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("scheduled_request_conflict")
        return request_id

    def is_active_scheduled_request(self, request_id: str, execution_session_id: str) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT 1 FROM scheduled_runs r JOIN scheduled_tasks t ON t.task_id = r.task_id "
                "WHERE r.request_id = ? AND r.status = 'running' "
                "AND t.execution_session_id = ? LIMIT 1",
                (request_id, execution_session_id),
            ).fetchone()
        return row is not None

    def finish_scheduled_run(
        self,
        run_id: str,
        status: str,
        now: datetime,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE scheduled_runs SET status = ?, completed_at = ?, error_kind = ?, "
                "error_message = ? WHERE run_id = ? AND status = 'running'",
                (status, utc_text(now), error_kind, error_message, run_id),
            )
