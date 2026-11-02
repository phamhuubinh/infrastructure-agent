"""Atomic owner-scoped skill catalogs and immutable resources inside managed SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime

from orion.contracts.skills import SkillDescriptor
from orion.skills.packages import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_RESOURCE_BYTES,
    SkillPackage,
    package_digest,
)


class SkillPersistence:
    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _create_skill_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS skill_packages (
                    digest TEXT PRIMARY KEY, manifest_json TEXT NOT NULL,
                    instructions TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_resources (
                    digest TEXT NOT NULL REFERENCES skill_packages(digest) ON DELETE CASCADE,
                    path TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    content BLOB NOT NULL, PRIMARY KEY(digest,path)
                );
                CREATE TABLE IF NOT EXISTS skill_catalog (
                    principal_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('bundled','user','project')),
                    project_key TEXT NOT NULL, name TEXT NOT NULL,
                    digest TEXT NOT NULL REFERENCES skill_packages(digest),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    PRIMARY KEY(principal_id,workspace_id,source,project_key,name)
                );
                CREATE INDEX IF NOT EXISTS skills_owner ON skill_catalog(principal_id,workspace_id);
            """)

    def install_skill(
        self, package: SkillPackage, principal: str, workspace: str, *, enabled: bool = True
    ) -> None:
        descriptor = package.descriptor
        if (
            not principal
            or not workspace
            or package_digest(package.resources) != descriptor.package_sha256
        ):
            raise ValueError("Skill installation identity is invalid")
        manifest = json.dumps(
            descriptor.model_dump(exclude={"source", "project_id", "enabled"}),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = descriptor.package_sha256
        project = descriptor.project_id or ""
        with self._lock, self._connection:
            current = self._connection.execute(
                "SELECT digest FROM skill_catalog WHERE principal_id=? AND workspace_id=? "
                "AND source=? AND project_key=? AND name=?",
                (principal, workspace, descriptor.source, project, descriptor.name),
            ).fetchone()
            count = self._connection.execute(
                "SELECT count(*) FROM skill_catalog WHERE principal_id=? AND workspace_id=?",
                (principal, workspace),
            ).fetchone()[0]
            if current is None and count >= 64:
                raise ValueError("Skill catalog capacity is unavailable")
            existing = self._connection.execute(
                "SELECT manifest_json,instructions FROM skill_packages WHERE digest=?", (digest,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["manifest_json"] != manifest
                    or existing["instructions"] != package.instructions
                ):
                    raise ValueError("Immutable skill identity mismatch")
                if self.skill_package_resources(digest) != package.resources:
                    raise ValueError("Immutable skill resources mismatch")
            else:
                self._connection.execute(
                    "INSERT INTO skill_packages VALUES (?,?,?,?)",
                    (digest, manifest, package.instructions, datetime.now(UTC).isoformat()),
                )
                self._connection.executemany(
                    "INSERT INTO skill_resources VALUES (?,?,?,?,?)",
                    [
                        (digest, name, len(data), hashlib.sha256(data).hexdigest(), data)
                        for name, data in sorted(package.resources.items())
                    ],
                )
            self._connection.execute(
                "INSERT INTO skill_catalog VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(principal_id,workspace_id,source,project_key,name) "
                "DO UPDATE SET digest=excluded.digest,enabled=excluded.enabled",
                (
                    principal,
                    workspace,
                    descriptor.source,
                    project,
                    descriptor.name,
                    digest,
                    int(enabled),
                ),
            )

    def skill_catalog(
        self, principal: str, workspace: str, project_id: str | None = None
    ) -> list[SkillDescriptor]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT c.*,p.manifest_json FROM skill_catalog c "
                "JOIN skill_packages p ON c.digest=p.digest "
                "WHERE c.principal_id=? AND c.workspace_id=? "
                "AND (c.project_key='' OR (c.source='project' AND c.project_key=?)) "
                "ORDER BY c.source,c.name",
                (principal, workspace, project_id or ""),
            ).fetchall()
        return [
            SkillDescriptor.model_validate(
                {
                    **json.loads(row["manifest_json"]),
                    "source": row["source"],
                    "project_id": row["project_key"] or None,
                    "enabled": bool(row["enabled"]),
                }
            )
            for row in rows
        ]

    def skill_package_resources(self, digest: str) -> dict[str, bytes]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT substr(path,1,513) AS path,length(path) AS path_length,bytes,sha256,"
                "length(content) AS content_length,substr(content,1,?) AS content "
                "FROM skill_resources "
                "WHERE digest=? ORDER BY path LIMIT ?",
                (MAX_RESOURCE_BYTES + 1, digest, MAX_PACKAGE_FILES + 1),
            ).fetchall()
        if (
            len(rows) > MAX_PACKAGE_FILES
            or sum(row["content_length"] for row in rows) > MAX_PACKAGE_BYTES
        ):
            raise ValueError("Skill package size is unavailable")
        result: dict[str, bytes] = {}
        for row in rows:
            content = bytes(row["content"])
            if (
                row["path_length"] > 512
                or row["content_length"] > MAX_RESOURCE_BYTES
                or len(content) != row["bytes"]
                or len(content) != row["content_length"]
                or hashlib.sha256(content).hexdigest() != row["sha256"]
            ):
                raise ValueError("Skill resource integrity is unavailable")
            result[row["path"]] = content
        if not result or package_digest(result) != digest:
            raise ValueError("Skill package integrity is unavailable")
        return result

    def set_skill_enabled(
        self,
        principal: str,
        workspace: str,
        source: str,
        project_id: str | None,
        name: str,
        enabled: bool,
    ) -> bool:
        with self._lock, self._connection:
            return (
                self._connection.execute(
                    "UPDATE skill_catalog SET enabled=? WHERE principal_id=? AND workspace_id=? "
                    "AND source=? AND project_key=? AND name=?",
                    (int(enabled), principal, workspace, source, project_id or "", name),
                ).rowcount
                == 1
            )

    def remove_skill(
        self, principal: str, workspace: str, source: str, project_id: str | None, name: str
    ) -> bool:
        if source not in {"user", "project"}:
            raise ValueError("Bundled skills can be disabled, not removed")
        with self._lock, self._connection:
            return (
                self._connection.execute(
                    "DELETE FROM skill_catalog WHERE principal_id=? AND workspace_id=? "
                    "AND source=? AND project_key=? AND name=?",
                    (principal, workspace, source, project_id or "", name),
                ).rowcount
                == 1
            )

    def collect_unused_skills(self, pinned: set[str]) -> None:
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT digest FROM skill_packages WHERE NOT EXISTS "
                "(SELECT 1 FROM skill_catalog c WHERE c.digest=skill_packages.digest)"
            ).fetchall()
            for row in rows:
                if row["digest"] not in pinned:
                    self._connection.execute(
                        "DELETE FROM skill_packages WHERE digest=?", (row["digest"],)
                    )
