from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.investigation_request import InvestigationRequest


class DeterministicAgent:
    """End-to-end deterministic investigation agent.

    Combines the deterministic pipeline with assessment.
    This is the replacement for the legacy ReAct Agent.

    Responsibilities:
    - run the deterministic pipeline (Intent → Evidence)
    - convert results to AssessmentRequest
    - build assessment prompt
    - send to model
    - return assessment

    The legacy ReAct path remains available for backward compatibility.
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        assessment_model: AssessmentModelAdapter,
    ) -> None:
        self._execution_engine = execution_engine
        self._assessment_model = assessment_model
        self._assessment_adapter = AssessmentAdapter()

    def run(self, user_request: str) -> str:
        """Run a full deterministic investigation and return assessment.

        Args:
            user_request: The raw user request.

        Returns:
            Assessment string from the model.
        """
        investigation = self._execution_engine.execute(user_request)
        assessment_request = self._assessment_adapter.build(investigation)
        return self._assessment_model.assess(assessment_request)

    def execute_pipeline_only(
        self,
        user_request: str,
    ) -> InvestigationRequest:
        """Run only the deterministic pipeline without assessment.

        Useful for debugging and benchmarking.
        """
        return self._execution_engine.execute(user_request)
