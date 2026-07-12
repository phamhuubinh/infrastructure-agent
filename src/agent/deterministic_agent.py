from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.intent_resolver import Confidence
from src.pipeline.intent_resolver import Intent


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

    def classify(self, user_request: str) -> tuple[bool, str | None]:
        """Classify whether a question is infrastructure-related.

        Two-tier approach:
        1. Keyword-based IntentResolver (fast, no model call).
           If confidence is HIGH or MEDIUM → infra = True.
        2. If confidence is LOW → ask the model directly (cheap classifier call).
           Model says 'yes' → infra = True, 'no' → infra = False.

        Returns:
            (is_infra: bool, reason: str | None)
            reason is set to "chat" if classified as general chat.
        """
        from src.pipeline.intent_resolver import IntentResolver
        resolver = IntentResolver()
        request = resolver.resolve(user_request)

        # Tier 1: keyword matching is confident enough
        if request.confidence in (Confidence.HIGH, Confidence.MEDIUM):
            return (True, None)

        # Tier 2: ask the model (fallback for LOW confidence / no keywords)
        classifier_prompt = (
            "Classify this user question as either:\n"
            "- 'infrastructure' if it asks about checking, monitoring, diagnosing, "
            "configuring, or investigating a real computer system, server, network, "
            "service, or IT infrastructure\n"
            "- 'general' if it's a casual chat, general knowledge, trivia, or "
            "anything not related to real IT systems\n\n"
            "Reply with exactly one word: infrastructure or general\n\n"
            f"Question: {user_request}\n\nAnswer:"
        )
        try:
            answer = self._assessment_model.assess_raw(classifier_prompt)
            answer_clean = answer.strip().lower()[:20]
            return (answer_clean.startswith("infrastructure"), None)
        except Exception:
            return (False, "chat")

    def chat(self, user_request: str) -> str:
        """Send a free-form chat message to the model without pipeline context.

        Args:
            user_request: The raw user message.

        Returns:
            The model's response string.
        """
        try:
            prompt = (
                "You are a helpful AI assistant. Answer the user's question "
                "concisely and accurately. If the question is about infrastructure "
                "or system administration, provide technical detail. "
                "Otherwise, answer as a general-purpose assistant.\n\n"
                f"User: {user_request}\n\nAssistant:"
            )
            return self._assessment_model.assess_raw(prompt)
        except Exception as exc:
            return f"Sorry, I couldn't process that: {exc}"

    def execute_pipeline_only(
        self,
        user_request: str,
    ) -> InvestigationRequest:
        """Run only the deterministic pipeline without assessment.

        Useful for debugging and benchmarking.
        """
        return self._execution_engine.execute(user_request)
