"""Persistent metadata store for isolated RAG projects."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectNotFoundError(KeyError):
    pass


class ProjectStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir = self.data_dir / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.data_dir / "projects.json"
        self._lock = threading.RLock()
        self._projects: dict[str, dict[str, Any]] = {}
        self._load()
        self.ensure_default()

    def ensure_default(self) -> dict[str, Any]:
        with self._lock:
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
                self._projects.values(),
                key=lambda item: str(item.get("updated_at", "")),
                reverse=True,
            )
            return deepcopy(projects)

    def get(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return deepcopy(self._projects[project_id])
            except KeyError as exc:
                raise ProjectNotFoundError(project_id) from exc

    def add_document(self, project_id: str, document: dict[str, Any]) -> None:
        with self._lock:
            project = self._require(project_id)
            project["documents"].append(deepcopy(document))
            project["updated_at"] = _now()
            self._save()

    def get_document(self, project_id: str, doc_id: str) -> dict[str, Any] | None:
        project = self.get(project_id)
        for document in project["documents"]:
            if document.get("id") == doc_id:
                return document
        return None

    def remove_document(self, project_id: str, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
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
            project = self._require(project_id)
            project["analyses"].insert(0, deepcopy(analysis))
            del project["analyses"][100:]
            project["updated_at"] = _now()
            self._save()

    def delete(self, project_id: str) -> bool:
        if project_id == "default":
            return False
        with self._lock:
            if self._projects.pop(project_id, None) is None:
                return False
            self._save()
        project_documents = self.documents_dir / project_id
        if project_documents.exists():
            shutil.rmtree(project_documents)
        return True

    def project_documents_dir(self, project_id: str) -> Path:
        self.get(project_id)
        path = self.documents_dir / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _require(self, project_id: str) -> dict[str, Any]:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(project_id) from exc

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict):
            self._projects = {
                str(key): value for key, value in raw.items() if isinstance(value, dict)
            }

    def _save(self) -> None:
        temp_path = self._path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(self._projects, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._path)
