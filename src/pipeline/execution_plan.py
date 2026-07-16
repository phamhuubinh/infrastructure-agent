from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from types import MappingProxyType

from src.pipeline.capability_reference import CapabilityReference


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    """One unit of investigation work.

    An ExecutionStep represents one operational capability that must
    eventually be executed. It is a description of work, not a runtime
    instruction.

    It does NOT contain:
    - parallel execution information
    - execution priority
    - graph edges or dependencies
    - tool routing
    - execution state
    - retry information
    - runtime flags

    Attributes:
        capability: The capability to execute.
        step_id: Optional unique identifier for this step.
        metadata: Immutable mapping for future extension.
    """

    capability: CapabilityReference
    step_id: str = ""
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Ordered list of investigation work.

    The plan defines what work must eventually be executed, in the
    order it was requested. It does NOT define how the runtime should
    execute that work.

    The plan is NOT a scheduler.
    The plan is NOT a graph.
    The plan is NOT an execution policy.

    Responsibilities:
    - enumerate all capabilities that must be executed
    - preserve insertion order
    - remove duplicate capabilities

    Attributes:
        steps: Ordered list of execution steps.
    """

    steps: tuple[ExecutionStep, ...] = ()
