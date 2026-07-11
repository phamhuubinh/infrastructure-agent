from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_plan import ExecutionPlan
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.investigation_request import InvestigationRequest


class ExecutionPlanner:
    """Plan investigation work.

    Responsibilities:
    - convert capability references into ordered execution steps
    - deduplicate identical capabilities
    - populate InvestigationRequest with an ExecutionPlan

    Does NOT:
    - create execution groups or batches
    - decide parallelism
    - assign priorities
    - create graph edges
    - schedule execution
    """

    def plan(self, request: InvestigationRequest) -> None:
        """Build an ExecutionPlan from capability references.

        Reads capability_references from the request.
        Produces a flat ordered list of execution steps.
        Duplicate capabilities (same name) are removed.

        Args:
            request: The InvestigationRequest. Must have capability_references
                     populated. Mutates execution_plan.
        """
        refs = request.capability_references

        if not refs:
            request.execution_plan = ExecutionPlan()
            return

        seen: set[str] = set()
        steps: list[ExecutionStep] = []

        for ref in refs:
            if ref.name in seen:
                continue
            seen.add(ref.name)
            steps.append(ExecutionStep(capability=ref))

        request.execution_plan = ExecutionPlan(steps=tuple(steps))
