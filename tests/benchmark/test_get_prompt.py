from __future__ import annotations

from unittest import mock

from benchmark.__main__ import _get_prompt

_END_MARKER = "--- End ---"
_EV_START = "--- Evidence ---"


def test_get_prompt_without_investigation_fallback() -> None:
    prompt = _get_prompt("check cpu", investigation=None)
    assert _EV_START in prompt
    assert _END_MARKER in prompt
    between = prompt.split(_EV_START)[1].split(_END_MARKER)[0]
    assert between.strip() == "", f"Expected empty evidence, got: {between[:100]}"


def test_get_prompt_with_investigation_includes_evidence() -> None:
    from src.pipeline.evidence_package import EvidencePackage
    from src.pipeline.investigation_request import InvestigationRequest

    packages = [
        EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU Hardware",
            data={"model": "Intel", "cores": 4},
            success=True,
        ),
        EvidencePackage(
            capability_name="Memory Information",
            evidence_name="Memory",
            data={"total_gb": 16, "usage_percent": 45},
            success=True,
        ),
    ]
    investigation = InvestigationRequest(
        raw_request="check cpu",
        evidence=packages,
        evidence_complete=True,
        missing_evidence=(),
    )

    prompt = _get_prompt("check cpu", investigation=investigation)
    assert _EV_START in prompt
    assert _END_MARKER in prompt
    between = prompt.split(_EV_START)[1].split(_END_MARKER)[0]
    assert "CPU Information" in between
    assert "Memory Information" in between


def test_get_prompt_with_investigation_skips_failed_evidence() -> None:
    from src.pipeline.evidence_package import EvidencePackage
    from src.pipeline.investigation_request import InvestigationRequest

    packages = [
        EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU Hardware",
            data=None,
            success=False,
            error="Something went wrong",
        ),
    ]
    investigation = InvestigationRequest(
        raw_request="check cpu",
        evidence=packages,
        evidence_complete=False,
        missing_evidence=("CPU Hardware",),
    )

    prompt = _get_prompt("check cpu", investigation=investigation)
    between = prompt.split(_EV_START)[1].split(_END_MARKER)[0]
    assert "CPU Information" not in between, "Failed evidence should be excluded"


@mock.patch("src.pipeline.assessment_adapter.AssessmentAdapter")
def test_get_prompt_investigation_fallback_on_error(
    mock_adapter_cls: mock.Mock,
) -> None:
    from src.pipeline.investigation_request import InvestigationRequest

    mock_instance = mock.Mock()
    mock_instance.build.side_effect = Exception("adapter error")
    mock_adapter_cls.return_value = mock_instance

    investigation = InvestigationRequest(raw_request="test")
    prompt = _get_prompt("check cpu", investigation=investigation)
    assert isinstance(prompt, str)
    assert len(prompt) > 0
