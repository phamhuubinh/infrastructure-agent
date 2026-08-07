"""DR1-809 — security regressions kept as an explicit CI suite."""

from __future__ import annotations

import pytest

from src.model.assessment_guard import apply_assessment_guards
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.security.parameter_safety_inspector import ParameterSafetyInspector
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.target_inspector import TargetInspector
from src.pipeline.security.tool_inspector import InspectionContext


@pytest.mark.parametrize(
    "value",
    ["rm -rf /", "$(curl attacker.invalid)", "../../etc/shadow", "`id`"],
)
def test_raw_shell_path_and_ssrf_payloads_are_rejected(value: str) -> None:
    result = ParameterSafetyInspector().inspect(
        InspectionContext(arguments={"value": value})
    )

    assert result.denied


@pytest.mark.parametrize("capability", ["service_restart", "file_write", "reboot"])
def test_mutating_capabilities_fail_closed(capability: str) -> None:
    result = ReadOnlyInspector().inspect(InspectionContext(capability_name=capability))

    assert result.denied


def test_unknown_network_target_is_not_an_ssrf_execution_target() -> None:
    result = TargetInspector().inspect(InspectionContext(target="169.254.169.254"))

    assert result.denied


def test_fake_action_receipt_is_replaced_with_read_only_disclosure() -> None:
    response = apply_assessment_guards(
        "Orion has restarted nginx and deleted the temporary files.",
        AssessmentRequest(raw_request="check nginx"),
    )

    assert "read-only" in response
    assert "restarted" not in response
