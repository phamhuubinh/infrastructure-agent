from __future__ import annotations

import hashlib
import json

from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action


def _normalize_arguments(args: dict[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted((k, v) for k, v in args.items() if k not in ("action",)))


def _observation_key(obs: Observation) -> str:
    tool = obs.tool
    normalized = _normalize_arguments(obs.arguments)
    raw = f"{tool}:{json.dumps(normalized, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode()).hexdigest()


class ReasoningState:
    """
    Manages execution state for a single reasoning session.

    Responsibilities:
    - Observation storage and lifecycle
    - Call history tracking for deduplication

    NOT responsible for:
    - Evidence extraction
    - Known facts generation
    - Infrastructure semantics

    Lifetime: exactly one user request. Destroyed after FinalResponse.
    """

    def __init__(self) -> None:
        self._observations: tuple[Observation, ...] = ()
        self._call_history: set[str] = set()

    @property
    def observations(self) -> tuple[Observation, ...]:
        return self._observations

    def add_observation(self, obs: Observation) -> None:
        self._observations += (obs,)
        if obs.success and obs.data is not None:
            self._call_history.add(_observation_key(obs))

    def was_executed(self, action: Action) -> bool:
        tool = action.tool
        normalized = _normalize_arguments(action.arguments)
        key = hashlib.md5(
            f"{tool}:{json.dumps(normalized, sort_keys=True, default=str)}".encode()
        ).hexdigest()
        return key in self._call_history

    def clear(self) -> None:
        self._observations = ()
        self._call_history = set()
