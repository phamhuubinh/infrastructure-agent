from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from src.shared.execution.environment_status import EnvironmentStatus


class ExecutionEnvironment:
    """
    ExecutionEnvironment manages the runtime resources for a single execution.
    """

    def __init__(self) -> None:
        self._status = EnvironmentStatus.UNINITIALIZED
        self._resources: dict[str, object] = {}
        self._initialized = False

    def initialize(
        self,
        resources: dict[str, object] | None = None,
    ) -> EnvironmentStatus:
        """
        Initialize the execution environment.

        Raises:
            ValueError:
                If the environment has already been initialized.
        """
        if self._initialized:
            raise ValueError("Execution environment has already been initialized.")

        self._resources = dict(resources or {})
        self._status = EnvironmentStatus.READY
        self._initialized = True

        return self._status

    def get_status(self) -> EnvironmentStatus:
        """
        Return the current environment status.
        """
        return self._status

    def get_resources(self) -> Mapping[str, object]:
        """
        Return a read-only view of the runtime resources.
        """
        return MappingProxyType(self._resources)

    def cleanup(self) -> None:
        """
        Release all runtime resources.

        Cleanup is idempotent.
        """
        if self._status is EnvironmentStatus.RELEASED:
            return

        self._status = EnvironmentStatus.CLEANING

        self._resources.clear()

        self._status = EnvironmentStatus.RELEASED
