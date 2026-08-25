"""Project lifecycle operations owned by Orion application state."""

from __future__ import annotations

from typing import Any

from orion.persistence.sqlite import SQLiteStore


class ProjectService:
    """Creates Projects and their immutable session association without a second runtime."""

    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def create(
        self,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._store.create_project(name, description, instructions, metadata)

    def get(self, project_id: str) -> dict[str, Any] | None:
        return self._store.project(project_id)

    def list(self) -> list[dict[str, Any]]:
        return self._store.projects()

    def update(
        self,
        project_id: str,
        name: str,
        description: str | None,
        instructions: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._store.update_project(project_id, name, description, instructions, metadata)

    def create_session(self, project_id: str, principal_id: str, workspace_id: str) -> str:
        if self.get(project_id) is None:
            raise KeyError(project_id)
        return self._store.create_session(principal_id, workspace_id, project_id)
