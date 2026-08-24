"""Persistent metadata store for isolated RAG projects."""

from __future__ import annotations

import builtins
import json
import threading
import uuid
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectNotFoundError(KeyError):
    pass


class ProjectStoreCorruptError(RuntimeError):
    pass


class ProjectRecoveringError(RuntimeError):
    pass


class ProjectStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir = self.data_dir / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.data_dir / "projects.json"
        self._recovery_path = self.data_dir / "recovery.json"
        self._lock = threading.RLock()
        self._projects: dict[str, dict[str, Any]] = {}
        self._recovery: dict[str, dict[str, Any]] = {}
        self._corrupt = False
        self._load()
        self._load_recovery()
        if not self._corrupt:
            self.ensure_default()

    def ensure_default(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_mutable()
            if "default" not in self._projects:
                now = _now()
                self._projects["default"] = {
                    "id": "default",
                    "name": "Default project",
                    "description": "Compatibility project for legacy RAG endpoints.",
                    "documents": [],
                    "analyses": [],
                    "created_at": now,
                    "updated_at": now,
                }
                self._save()
            return deepcopy(self._projects["default"])

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        with self._lock:
            self._ensure_mutable()
            project_id = uuid.uuid4().hex[:16]
            now = _now()
            project = {
                "id": project_id,
                "name": name.strip(),
                "description": description.strip(),
                "documents": [],
                "analyses": [],
                "created_at": now,
                "updated_at": now,
            }
            self._projects[project_id] = project
            self._save()
            return deepcopy(project)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            projects = sorted(
                (
                    self._public_project(project)
                    for project in self._projects.values()
                    if project.get("state", "active") == "active"
                ),
                key=lambda item: str(item.get("updated_at", "")),
                reverse=True,
            )
            return deepcopy(projects)

    def get(
        self, project_id: str, *, include_recovering: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            try:
                project = self._projects[project_id]
            except KeyError as exc:
                raise ProjectNotFoundError(project_id) from exc
            if not include_recovering and project.get("state", "active") != "active":
                raise ProjectRecoveringError(project_id)
            return deepcopy(
                project if include_recovering else self._public_project(project)
            )

    def add_document(self, project_id: str, document: dict[str, Any]) -> None:
        with self._lock:
            self._ensure_mutable()
            project = self._require(project_id)
            stored = deepcopy(document)
            stored["state"] = "active"
            project["documents"].append(stored)
            project["updated_at"] = _now()
            self._save()

    def get_document(
        self, project_id: str, doc_id: str, *, include_recovering: bool = False
    ) -> dict[str, Any] | None:
        project = self.get(project_id, include_recovering=include_recovering)
        for document in project["documents"]:
            if document.get("id") == doc_id and (
                include_recovering or document.get("state", "active") == "active"
            ):
                return document
        return None

    def mark_document_deleting(self, project_id: str, doc_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_mutable()
            project = self._require(project_id)
            for document in project["documents"]:
                if document.get("id") == doc_id:
                    document["state"] = "deleting"
                    project["updated_at"] = _now()
                    self._save()
                    return deepcopy(document)
            raise ProjectNotFoundError(f"{project_id}/{doc_id}")

    def remove_document(self, project_id: str, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._ensure_mutable()
            project = self._require(project_id)
            for index, document in enumerate(project["documents"]):
                if document.get("id") == doc_id:
                    removed = project["documents"].pop(index)
                    project["updated_at"] = _now()
                    self._save()
                    return deepcopy(removed)
            return None

    def add_analysis(self, project_id: str, analysis: dict[str, Any]) -> None:
        with self._lock:
            self._ensure_mutable()
            project = self._require(project_id)
            project["analyses"].insert(0, deepcopy(analysis))
            del project["analyses"][100:]
            project["updated_at"] = _now()
            self._save()

    def mark_project_deleting(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_mutable()
            project = self._require(project_id)
            project["state"] = "deleting"
            project["updated_at"] = _now()
            self._save()
            return deepcopy(project)

    def delete(self, project_id: str) -> bool:
        if project_id == "default":
            return False
        with self._lock:
            self._ensure_mutable()
            if self._projects.pop(project_id, None) is None:
                return False
            self._save()
        return True

    def project_documents_dir(self, project_id: str) -> Path:
        self.get(project_id)
        path = self.documents_dir / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def staging_documents_dir(self, project_id: str) -> Path:
        self.get(project_id, include_recovering=True)
        path = self.data_dir / "staging" / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def begin_recovery(self, operation: str, **data: Any) -> dict[str, Any]:
        """Persist a recovery record before the first cross-store mutation."""
        with self._lock:
            self._ensure_mutable()
            record_id = uuid.uuid4().hex
            record = {
                "id": record_id,
                "operation": operation,
                "created_at": _now(),
                "updated_at": _now(),
                **deepcopy(data),
            }
            self._recovery[record_id] = record
            self._save_recovery()
            return deepcopy(record)

    def update_recovery(self, record_id: str, **data: Any) -> dict[str, Any]:
        with self._lock:
            self._ensure_mutable()
            record = self._recovery[record_id]
            record.update(deepcopy(data))
            record["updated_at"] = _now()
            self._save_recovery()
            return deepcopy(record)

    def recovery_records(
        self, project_id: str | None = None
    ) -> builtins.list[dict[str, Any]]:
        with self._lock:
            records: Iterable[dict[str, Any]] = self._recovery.values()
            if project_id is not None:
                records = (
                    record for record in records if record.get("project_id") == project_id
                )
            return deepcopy(builtins.list(records))

    def resolve_recovery(self, record_id: str) -> None:
        with self._lock:
            self._ensure_mutable()
            self._recovery.pop(record_id, None)
            self._save_recovery()

    def _require(self, project_id: str) -> dict[str, Any]:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(project_id) from exc

    @staticmethod
    def _public_project(project: dict[str, Any]) -> dict[str, Any]:
        visible = deepcopy(project)
        visible.pop("state", None)
        visible["documents"] = [
            {key: value for key, value in document.items() if key != "state"}
            for document in visible.get("documents", [])
            if document.get("state", "active") == "active"
        ]
        return visible

    def _ensure_mutable(self) -> None:
        if self._corrupt:
            raise ProjectStoreCorruptError(
                "Project or recovery metadata is corrupt; mutation is disabled."
            )

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._corrupt = True
            return
        if not isinstance(raw, dict) or any(not isinstance(value, dict) for value in raw.values()):
            self._corrupt = True
            return
        self._projects = {str(key): value for key, value in raw.items()}

    def _load_recovery(self) -> None:
        if not self._recovery_path.exists():
            return
        try:
            raw = json.loads(self._recovery_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._corrupt = True
            return
        if not isinstance(raw, dict) or any(not isinstance(value, dict) for value in raw.values()):
            self._corrupt = True
            return
        self._recovery = {str(key): value for key, value in raw.items()}

    def _save(self) -> None:
        temp_path = self._path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(self._projects, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._path)

    def _save_recovery(self) -> None:
        temp_path = self._recovery_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(self._recovery, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._recovery_path)
