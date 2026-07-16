from __future__ import annotations

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_plan import ExecutionPlan
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest


@pytest.fixture
def planner() -> ExecutionPlanner:
    return ExecutionPlanner()


def _request(refs: list[CapabilityReference]) -> InvestigationRequest:
    req = InvestigationRequest(raw_request="test", intent=Intent.MACHINE_ASSESSMENT)
    req.capability_references = refs
    return req


def _ref(name: str, evidence: str = "") -> CapabilityReference:
    return CapabilityReference(name=name, evidence_name=evidence or name)


def _step_names(plan: ExecutionPlan) -> list[str]:
    return [s.capability.name for s in plan.steps]


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


class TestEmptyPlan:
    def test_no_references(self, planner: ExecutionPlanner) -> None:
        req = _request([])
        planner.plan(req)
        assert req.execution_plan is not None
        assert req.execution_plan.steps == ()

    def test_single_capability(self, planner: ExecutionPlanner) -> None:
        req = _request([_ref("CPU Information")])
        planner.plan(req)
        assert req.execution_plan is not None
        assert _step_names(req.execution_plan) == ["CPU Information"]


# ---------------------------------------------------------------------------
# Order — plan preserves insertion order
# ---------------------------------------------------------------------------


class TestOrder:
    def test_preserves_insertion_order(self, planner: ExecutionPlanner) -> None:
        req = _request(
            [
                _ref("Service Status"),
                _ref("CPU Information"),
                _ref("System Information"),
            ]
        )
        planner.plan(req)
        assert _step_names(req.execution_plan) == [
            "Service Status",
            "CPU Information",
            "System Information",
        ]

    def test_order_is_deterministic(self, planner: ExecutionPlanner) -> None:
        refs = [
            _ref("Service Status"),
            _ref("CPU Information"),
            _ref("System Information"),
        ]
        req1 = _request(list(refs))
        req2 = _request(list(refs))
        planner.plan(req1)
        planner.plan(req2)
        assert req1.execution_plan == req2.execution_plan


# ---------------------------------------------------------------------------
# Duplicate removal
# ---------------------------------------------------------------------------


class TestDuplicateRemoval:
    def test_identical_capabilities_deduplicated(
        self, planner: ExecutionPlanner
    ) -> None:
        req = _request(
            [
                _ref("CPU Information"),
                _ref("CPU Information"),
            ]
        )
        planner.plan(req)
        assert _step_names(req.execution_plan) == ["CPU Information"]
        assert len(req.execution_plan.steps) == 1

    def test_identical_capability_three_times(self, planner: ExecutionPlanner) -> None:
        req = _request(
            [
                _ref("CPU Information"),
                _ref("CPU Information"),
                _ref("CPU Information"),
            ]
        )
        planner.plan(req)
        assert _step_names(req.execution_plan) == ["CPU Information"]
        assert len(req.execution_plan.steps) == 1

    def test_first_occurrence_preserved(self, planner: ExecutionPlanner) -> None:
        req = _request(
            [
                _ref("CPU Information", evidence="CPU"),
                _ref("CPU Information", evidence="CPU Usage"),
            ]
        )
        planner.plan(req)
        assert len(req.execution_plan.steps) == 1
        assert req.execution_plan.steps[0].capability.evidence_name == "CPU"

    def test_multiple_capabilities_with_duplicates(
        self, planner: ExecutionPlanner
    ) -> None:
        req = _request(
            [
                _ref("CPU Information"),
                _ref("Service Status"),
                _ref("CPU Information"),
                _ref("Package Discovery"),
                _ref("Service Status"),
            ]
        )
        planner.plan(req)
        assert _step_names(req.execution_plan) == [
            "CPU Information",
            "Service Status",
            "Package Discovery",
        ]
        assert len(req.execution_plan.steps) == 3


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_plan_is_idempotent(self, planner: ExecutionPlanner) -> None:
        req = _request([_ref("CPU Information"), _ref("Service Status")])
        planner.plan(req)
        first = req.execution_plan
        planner.plan(req)
        assert req.execution_plan == first


# ---------------------------------------------------------------------------
# ExecutionStep properties
# ---------------------------------------------------------------------------


class TestExecutionStep:
    def test_minimal(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref)
        assert step.capability.name == "CPU Information"
        assert step.step_id == ""
        assert step.metadata == {}

    def test_with_step_id(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref, step_id="step-1")
        assert step.step_id == "step-1"

    def test_with_metadata(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref, metadata={"domain": "linux"})
        assert step.metadata["domain"] == "linux"

    def test_immutable(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref)
        with pytest.raises(AttributeError):
            step.step_id = "new-id"  # type: ignore[misc]

    def test_repr(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref, step_id="s1")
        assert "ExecutionStep" in repr(step)
        assert "CPU Information" in repr(step)


# ---------------------------------------------------------------------------
# ExecutionPlan properties
# ---------------------------------------------------------------------------


class TestExecutionPlan:
    def test_empty_plan(self) -> None:
        p = ExecutionPlan()
        assert p.steps == ()

    def test_immutable(self) -> None:
        p = ExecutionPlan()
        with pytest.raises(AttributeError):
            p.steps = ()  # type: ignore[misc]

    def test_multiple_steps(self) -> None:
        s1 = ExecutionStep(capability=_ref("CPU Information"))
        s2 = ExecutionStep(capability=_ref("Service Status"))
        p = ExecutionPlan(steps=(s1, s2))
        assert len(p.steps) == 2
        assert p.steps[0].capability.name == "CPU Information"
        assert p.steps[1].capability.name == "Service Status"


# ---------------------------------------------------------------------------
# No grouping — ExecutionPlan must remain flat
# ---------------------------------------------------------------------------


class TestNoGrouping:
    """ExecutionPlan must NOT contain groups, batches, or scheduling info."""

    def test_plan_has_no_groups_attribute(self) -> None:
        p = ExecutionPlan()
        assert not hasattr(p, "groups")

    def test_plan_has_no_parallel_groups_attribute(self) -> None:
        p = ExecutionPlan()
        assert not hasattr(p, "parallel_groups")

    def test_step_has_no_dependencies(self) -> None:
        ref = _ref("CPU Information")
        step = ExecutionStep(capability=ref)
        assert not hasattr(step, "depends_on")
        assert not hasattr(step, "parallel")
        assert not hasattr(step, "priority")
        assert not hasattr(step, "retry")


# ---------------------------------------------------------------------------
# Integration — full pipeline evidence → plan
# ---------------------------------------------------------------------------


class TestFullPipelineEvidenceToPlan:
    """Ensure ExecutionPlanner works with real capability references
    produced by CapabilityResolver."""

    def test_machine_assessment_plan(self, planner: ExecutionPlanner) -> None:
        from src.pipeline.capability_library import CAPABILITY_BY_EVIDENCE

        evidence_names = [
            "System Information",
            "CPU",
            "Memory",
            "Swap",
            "Storage",
            "Filesystem",
            "Network",
            "Services",
        ]
        refs: list[CapabilityReference] = []
        for ev_name in evidence_names:
            cap_name = CAPABILITY_BY_EVIDENCE[ev_name]
            refs.append(CapabilityReference(name=cap_name, evidence_name=ev_name))

        req = _request(refs)
        planner.plan(req)
        assert req.execution_plan is not None
        assert len(req.execution_plan.steps) == len(evidence_names)
        step_names = _step_names(req.execution_plan)
        expected_caps = {CAPABILITY_BY_EVIDENCE[e] for e in evidence_names}
        assert set(step_names) == expected_caps
