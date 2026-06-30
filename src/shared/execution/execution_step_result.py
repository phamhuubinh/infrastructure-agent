from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionStepResult:
    """
    Immutable execution step result.
    """

    result: object
