from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class BudgetStopReason(str, Enum):
    EVIDENCE_SUFFICIENT = "evidence_sufficient"
    NO_RECOVERABLE_PATH = "no_recoverable_path"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TARGET_TRANSPORT_FAILED = "target_transport_failed"


@dataclass(frozen=True, slots=True)
class ExecutionBudgetConfig:
    max_rounds: int = 2
    max_capabilities: int = 12
    max_total_duration: float = 120.0
    max_estimated_cost: float = 8.0

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        if self.max_capabilities < 1:
            raise ValueError("max_capabilities must be at least 1")
        if self.max_total_duration <= 0:
            raise ValueError("max_total_duration must be positive")
        if self.max_estimated_cost < 0:
            raise ValueError("max_estimated_cost must be non-negative")


@dataclass(slots=True)
class ExecutionBudget:
    """Per-investigation hard budget shared by primary and expansion rounds."""

    config: ExecutionBudgetConfig = field(default_factory=ExecutionBudgetConfig)
    rounds: int = 0
    capabilities: int = 0
    estimated_cost: float = 0.0
    stop_reason: BudgetStopReason | None = None
    _started_at: float = field(default_factory=time.perf_counter, repr=False)

    @property
    def elapsed(self) -> float:
        return max(time.perf_counter() - self._started_at, 0.0)

    @property
    def remaining_duration(self) -> float:
        return max(self.config.max_total_duration - self.elapsed, 0.0)

    @property
    def exhausted(self) -> bool:
        return (
            self.rounds >= self.config.max_rounds
            or self.capabilities >= self.config.max_capabilities
            or self.estimated_cost >= self.config.max_estimated_cost
            or self.remaining_duration <= 0
        )

    def can_start_round(self, capability_count: int, estimated_cost: float) -> bool:
        if capability_count < 0 or estimated_cost < 0:
            raise ValueError("budget reservation cannot be negative")
        allowed = (
            self.rounds < self.config.max_rounds
            and self.capabilities + capability_count
            <= self.config.max_capabilities
            and self.estimated_cost + estimated_cost
            <= self.config.max_estimated_cost
            and self.remaining_duration > 0
        )
        if not allowed:
            self.stop_reason = BudgetStopReason.BUDGET_EXHAUSTED
        return allowed

    def start_round(self, capability_count: int, estimated_cost: float) -> bool:
        if not self.can_start_round(capability_count, estimated_cost):
            return False
        self.rounds += 1
        self.capabilities += capability_count
        self.estimated_cost += estimated_cost
        return True

    def stop(
        self,
        *,
        evidence_sufficient: bool = False,
        recoverable_path: bool = True,
        transport_failed: bool = False,
    ) -> BudgetStopReason | None:
        if transport_failed:
            self.stop_reason = BudgetStopReason.TARGET_TRANSPORT_FAILED
        elif evidence_sufficient:
            self.stop_reason = BudgetStopReason.EVIDENCE_SUFFICIENT
        elif self.exhausted:
            self.stop_reason = BudgetStopReason.BUDGET_EXHAUSTED
        elif not recoverable_path:
            self.stop_reason = BudgetStopReason.NO_RECOVERABLE_PATH
        return self.stop_reason

    def to_dict(self) -> dict[str, object]:
        return {
            "max_rounds": self.config.max_rounds,
            "max_capabilities": self.config.max_capabilities,
            "max_total_duration": self.config.max_total_duration,
            "max_estimated_cost": self.config.max_estimated_cost,
            "rounds": self.rounds,
            "capabilities": self.capabilities,
            "estimated_cost": self.estimated_cost,
            "elapsed": self.elapsed,
            "remaining_duration": self.remaining_duration,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
        }
