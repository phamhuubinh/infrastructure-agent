"""Application-owned local access and principal identities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """A local application identity, never model-authored authority."""

    principal_id: str
    workspace_id: str


class LocalAccessAdapter:
    """The v1 loopback access baseline: exactly one built-in local principal."""

    _principal = Principal(principal_id="local", workspace_id="local")

    def current_principal(self) -> Principal:
        return self._principal

    def principal_for_session(self, principal_id: str, workspace_id: str) -> Principal:
        if (principal_id, workspace_id) != (
            self._principal.principal_id,
            self._principal.workspace_id,
        ):
            raise PermissionError("Session is not available to the local principal.")
        return self._principal
