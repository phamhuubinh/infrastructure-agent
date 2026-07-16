from __future__ import annotations

from unittest import mock

from src.model.assessment_result import AssessmentResult
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage


class TestLLMAssessmentAdapter:
    def test_assess_returns_string(self) -> None:
        client = mock.Mock(spec=LLMClient)
        client.generate.return_value = "System is healthy."
        client._model = "test-model"

        adapter = LLMAssessmentAdapter(client=client)
        req = AssessmentRequest(raw_request="check server")
        result = adapter.assess(req)
        assert result == "System is healthy."

    def test_assess_with_result_success(self) -> None:
        client = mock.Mock(spec=LLMClient)
        client.generate.return_value = "All systems OK."
        client._model = "test-model"

        adapter = LLMAssessmentAdapter(client=client)
        req = AssessmentRequest(raw_request="check server")
        result = adapter.assess_with_result(req)

        assert isinstance(result, AssessmentResult)
        assert result.content == "All systems OK."
        assert result.success is True
        assert result.model == "test-model"
        assert result.error is None
        # Latency may be 0 in mocked test (instant response)

    def test_assess_with_result_failure(self) -> None:
        client = mock.Mock(spec=LLMClient)
        client.generate.side_effect = RuntimeError("API timeout")
        client._model = "test-model"

        adapter = LLMAssessmentAdapter(client=client)
        req = AssessmentRequest(raw_request="check server")
        result = adapter.assess_with_result(req)

        assert isinstance(result, AssessmentResult)
        assert result.content == ""
        assert result.success is False
        assert result.error is not None
        assert "API timeout" in result.error

    def test_assess_with_evidence(self) -> None:
        client = mock.Mock(spec=LLMClient)
        client.generate.return_value = "CPU is healthy."
        client._model = "test-model"

        adapter = LLMAssessmentAdapter(client=client)
        req = AssessmentRequest(
            raw_request="check cpu",
            evidence=(
                EvidencePackage(
                    capability_name="CPU Information",
                    evidence_name="CPU",
                    success=True,
                    data={"cores": 4, "usage": 25},
                ),
            ),
        )
        result = adapter.assess(req)
        assert result == "CPU is healthy."

        # Verify prompt was built and sent
        client.generate.assert_called_once()
        prompt = client.generate.call_args[0][0]
        assert "CPU" in prompt
        assert "cores" in prompt

    def test_assess_empty_evidence(self) -> None:
        client = mock.Mock(spec=LLMClient)
        client.generate.return_value = "No evidence collected."
        client._model = "test-model"

        adapter = LLMAssessmentAdapter(client=client)
        req = AssessmentRequest(raw_request="check", evidence=())
        result = adapter.assess(req)
        assert result == "No evidence collected."


class TestAssessmentResult:
    def test_defaults(self) -> None:
        r = AssessmentResult()
        assert r.content == ""
        assert r.success is True
        assert r.model == ""
        assert r.error is None
        assert r.latency_ms == 0.0

    def test_frozen(self) -> None:
        r = AssessmentResult(content="ok")
        import pytest

        with pytest.raises(AttributeError):
            r.content = "changed"  # type: ignore[misc]
