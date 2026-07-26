from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto


class InspectionVerdict(Enum):
    """Verdict returned by a ToolInspector after inspecting a capability execution."""

    ALLOW = auto()
    """Execution is permitted. Continue to the next inspector."""

    DENY = auto()
    """Execution is blocked. Return an error without calling the handler."""

    REQUIRE_APPROVAL = auto()
    """Execution requires explicit approval before proceeding."""


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """Result of a single inspector's check.

    Attributes:
        verdict: Whether the execution is allowed, denied, or requires approval.
        reason: Human-readable explanation for the verdict.
        inspector_name: Name of the inspector that produced this result.
    """

    verdict: InspectionVerdict
    reason: str = ""
    inspector_name: str = ""

    @property
    def allowed(self) -> bool:
        """True if the execution is permitted."""
        return self.verdict == InspectionVerdict.ALLOW

    @property
    def denied(self) -> bool:
        """True if the execution is blocked."""
        return self.verdict == InspectionVerdict.DENY


@dataclass(frozen=True, slots=True)
class InspectionContext:
    """Context passed to inspectors for making decisions.

    Attributes:
        capability_name: The capability being invoked.
        target: The target server or source.
        resource: The resource or action being requested.
        arguments: Full arguments dict passed to the tool.
        tool_name: Name of the tool being dispatched to.
    """

    capability_name: str = ""
    target: str = ""
    resource: str = ""
    arguments: dict[str, object] = field(default_factory=dict)
    tool_name: str = ""


class ToolInspector(ABC):
    """Abstract base class for security inspectors in the pipeline.

    Inspectors run in a chain before every tool dispatch. Each inspector
    examines the execution context and returns an InspectionResult.
    The chain stops at the first DENY or REQUIRE_APPROVAL result.

    Implementations must be:
    - Deterministic: same input → same output.
    - Stateless: no mutable internal state between inspections.
    - Fast: each inspector should complete in <1ms.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this inspector, used in result metadata."""
        ...

    @abstractmethod
    def inspect(self, context: InspectionContext) -> InspectionResult:
        """Inspect a capability execution and return a verdict.

        Args:
            context: The execution context including capability, target,
                     resource, arguments, and tool name.

        Returns:
            An InspectionResult with the verdict and optional reason.
        """
        ...
