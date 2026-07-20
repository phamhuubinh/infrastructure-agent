from __future__ import annotations

from src.agent.conversation_store import ConversationStore
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.prompt_builder_v2 import (
    _normalize_evidence,
    build_assessment_prompt,
)
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.deterministic_responder import DeterministicResponder
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.intent_resolver import Confidence, Intent
from src.pipeline.investigation_request import InvestigationRequest
from src.shared.logger import warning as _warning
from src.tool.tool import Tool


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
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._assessment_model = assessment_model
        self._assessment_adapter = AssessmentAdapter()
        self._deterministic_responder = DeterministicResponder()
        self._conversation_store = conversation_store
        if self._conversation_store:
            self._conversation_store.set_summarize_fn(self._assessment_model.assess_raw)

    def run(self, user_request: str) -> str:
        """Run a full deterministic investigation and return assessment.

        Args:
            user_request: The raw user request.

        Returns:
            Assessment string from the model.
        """
        if self._is_knowledge_question(user_request):
            return self.chat(user_request)

        investigation = self._execution_engine.execute(user_request)
        return self._assess(user_request, investigation)

    def run_with_steps(self, user_request: str) -> dict:
        """Run pipeline + assessment, return structured result with steps.

        Single entry point for CLI and web. Returns a dict with:
          - response: assessment text
          - steps: list of pipeline step dicts for UI display
          - investigation: the InvestigationRequest (for CLI /evidence etc.)
        """
        if self._is_knowledge_question(user_request):
            return {
                "response": self.chat(user_request),
                "steps": [],
                "investigation": None,
            }

        investigation = self._execution_engine.execute(user_request)
        response = self._assess(user_request, investigation)
        steps = self._build_pipeline_steps(investigation)
        return {
            "response": response,
            "steps": steps,
            "investigation": investigation,
        }

    def _build_pipeline_steps(self, investigation: InvestigationRequest) -> list[dict]:
        """Serialize pipeline stages into step dicts for UI."""
        steps = []

        plan_steps = []
        if investigation.execution_plan:
            for step in investigation.execution_plan.steps:
                plan_steps.append(
                    {
                        "capability": step.capability.name,
                        "evidence": step.capability.evidence_name,
                    }
                )

        steps.append(
            {
                "type": "intent",
                "intent": investigation.intent.name if investigation.intent else "N/A",
                "confidence": investigation.confidence.name
                if investigation.confidence
                else "N/A",
                "target": investigation.target or "localhost",
                "matched_keywords": list(investigation.matched_keywords),
                "required_evidence": [e.name for e in investigation.required_evidence],
                "optional_evidence": [e.name for e in investigation.optional_evidence],
                "planned_capabilities": plan_steps,
            }
        )

        evidence_list = []
        for pkg in investigation.evidence:
            data_str = str(pkg.data) if pkg.data is not None else None
            truncated = _normalize_evidence(pkg.data)
            evidence_list.append(
                {
                    "capability": pkg.capability_name,
                    "evidence": pkg.evidence_name,
                    "success": pkg.success,
                    "error": pkg.error if not pkg.success else None,
                    "data_preview": data_str[:500] if data_str else None,
                    "data": truncated,
                }
            )

        metrics = investigation.runtime_metrics
        steps.append(
            {
                "type": "evidence",
                "collected": len(investigation.evidence),
                "successful": sum(1 for p in investigation.evidence if p.success),
                "failed": sum(1 for p in investigation.evidence if not p.success),
                "items": evidence_list,
                "complete": investigation.evidence_complete,
                "missing_evidence": list(investigation.missing_evidence),
                "runtime_metrics": {
                    "execution_duration": round(
                        getattr(metrics, "execution_duration", 0), 3
                    )
                    if metrics
                    else 0,
                    "total_nodes": getattr(metrics, "total_nodes", 0) if metrics else 0,
                    "successful_nodes": getattr(metrics, "successful_nodes", 0)
                    if metrics
                    else 0,
                    "failed_nodes": getattr(metrics, "failed_nodes", 0)
                    if metrics
                    else 0,
                    "parallel_ratio": round(getattr(metrics, "parallel_ratio", 0), 2)
                    if metrics
                    else 0,
                    "tool_calls": getattr(metrics, "tool_calls", 0) if metrics else 0,
                },
            }
        )

        assessment_request = self._assessment_adapter.build(investigation)
        prompt = build_assessment_prompt(assessment_request)
        steps.append(
            {
                "type": "prompt",
                "size": len(prompt),
                "preview": prompt[:500],
            }
        )

        return steps

    def _assess(self, user_request: str, investigation: InvestigationRequest) -> str:
        # Deterministic shortcuts: skip LLM if evidence is simple enough.
        deterministic = self._deterministic_responder.try_response(investigation)
        if deterministic is not None:
            if self._conversation_store:
                self._conversation_store.add_turn(user_request, deterministic)
            return deterministic

        assessment_request = self._assessment_adapter.build(investigation)

        if self._conversation_store:
            conv_history = self._conversation_store.history
            if conv_history:
                conv_text = "\n\n".join(
                    f"{m['role']}: {m['content']}" for m in conv_history
                )
                conv_prefix = f"--- Recent conversation context ---\n{conv_text}\n\n--- Current request ---\n{assessment_request.raw_request}"
                assessment_request = AssessmentRequest(
                    raw_request=conv_prefix,
                    intent=assessment_request.intent,
                    evidence=assessment_request.evidence,
                    evidence_complete=assessment_request.evidence_complete,
                    missing_evidence=assessment_request.missing_evidence,
                )

        response = self._assessment_model.assess(assessment_request)

        # Append tool-specific deep links when available.
        links = self._build_tool_links(investigation, user_request)
        if links:
            response += "\n\n---\n\n" + links

        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)

        return response

    def _is_knowledge_question(self, user_request: str) -> bool:
        """Check if the request is a general knowledge question (e.g. K8s)."""
        from src.pipeline.intent_resolver import IntentResolver as _Resolver

        _check = _Resolver()
        _req = _check.resolve(user_request)
        return _req.intent == Intent.KNOWLEDGE_ASSESSMENT

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
            is_infra = answer_clean.startswith("infrastructure")
            if self._conversation_store:
                label = "infrastructure" if is_infra else "general"
                self._conversation_store.add_classifier_turn(user_request, label)
            return (is_infra, None)
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
            system = (
                "You are a helpful AI assistant. Answer the user's question "
                "concisely and accurately. If the question is about infrastructure "
                "or system administration, provide technical detail. "
                "Otherwise, answer as a general-purpose assistant."
            )
            if self._conversation_store:
                conv_history = self._conversation_store.history
                if conv_history:
                    conv_text = "\n\n".join(
                        f"{m['role']}: {m['content']}" for m in conv_history
                    )
                    prompt = f"{conv_text}\n\nUser: {user_request}\n\nAssistant:"
                else:
                    prompt = f"{system}\n\nUser: {user_request}\n\nAssistant:"
            else:
                prompt = f"{system}\n\nUser: {user_request}\n\nAssistant:"

            response = self._assessment_model.assess_raw(prompt)
            if self._conversation_store:
                self._conversation_store.add_turn(user_request, response)
            return response
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

    def _build_tool_links(
        self,
        investigation: InvestigationRequest,
        user_request: str,
    ) -> str:
        """Build tool-specific deep links from collected evidence.

        Delegates to each tool's build_links() method.
        """
        parts = []
        kt = self._execution_engine.knowledge_tool
        evidence_list = list(investigation.evidence)
        for name in kt._registry.target_names():
            try:
                tool = kt._registry.get_tool(name)
                if isinstance(tool, Tool):
                    links = tool.build_links(evidence_list, user_request)
                    if links:
                        parts.append(links)
            except Exception:
                _warning("agent", message=f"failed to build links for tool {name}")
        return "\n\n".join(parts)
