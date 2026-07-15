from __future__ import annotations

from src.agent.conversation_store import ConversationStore
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
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
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._assessment_model = assessment_model
        self._assessment_adapter = AssessmentAdapter()
        self._conversation_store = conversation_store
        if self._conversation_store and not self._conversation_store._summarize_fn:
            self._conversation_store._summarize_fn = self._assessment_model.assess_raw

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

    def run_with_request(self, user_request: str, investigation: InvestigationRequest) -> str:
        """Run assessment from an already-completed investigation.
        
        Skips the pipeline execution and goes straight to assessment.
        Used by web API to avoid running the pipeline twice.
        """
        return self._assess(user_request, investigation)

    def _assess(self, user_request: str, investigation: InvestigationRequest) -> str:
        # Deterministic shortcuts: skip LLM if evidence is simple enough.
        deterministic = self._try_deterministic_response(investigation)
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

        # Append Grafana panel links when monitoring dashboards are in evidence.
        grafana_links = self._build_grafana_links(investigation, user_request)
        if grafana_links:
            response += "\n\n---\n\n" + grafana_links

        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)

        return response

    def _build_messages_prompt(self, messages: list[dict[str, str]]) -> str:
        lines = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                lines.append(f"Context: {content}")
            elif role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
        return "\n\n".join(lines)

    def _is_knowledge_question(self, user_request: str) -> bool:
        """Check if the request is a general knowledge question (e.g. K8s)."""
        from src.pipeline.intent_resolver import IntentResolver as _Resolver
        _check = _Resolver()
        _req = _check.resolve(user_request)
        return _req.intent == Intent.KNOWLEDGE_ASSESSMENT

    def _try_deterministic_response(
        self,
        investigation: InvestigationRequest,
    ) -> str | None:
        """Return a deterministic answer without LLM call when possible.

        Checks for:
        - Zombie process count (PROCESS_ASSESSMENT)
        - Failed services (when user only asks about status)
        """
        raw = investigation.raw_request.lower()
        is_service_status = any(
            kw in raw for kw in ("status", "trạng thái", "chạy", "die", "down")
        ) and any(
            kw in raw for kw in ("service", "dịch vụ", "sshd", "nginx")
        )

        for pkg in investigation.evidence:
            if not pkg.success or not isinstance(pkg.data, dict):
                continue

            # Zombie process detection
            if pkg.evidence_name == "Processes":
                zombies = (
                    pkg.data.get("zombie_count") or
                    pkg.data.get("zombie") or
                    pkg.data.get("zombies") or
                    0
                )
                if isinstance(zombies, (int, float)) and zombies > 0:
                    truncated = ""

                    zombie_processes = pkg.data.get("zombie_processes") or []
                    if zombie_processes:
                        truncated_list = list(zombie_processes)[:5]
                        truncated = f": {', '.join(str(p) for p in truncated_list)}"
                        if len(zombie_processes) > 5:
                            truncated += f" (+{len(zombie_processes) - 5} more)"

                    return (
                        f"## Zombie Process Detected\n\n"
                        f"There {'are' if zombies > 1 else 'is'} **{int(zombies)} zombie "
                        f"process{'es' if zombies > 1 else ''}** on this system{truncated}.\n\n"
                        f"Zombie processes consume process table entries (PID) and may indicate "
                        f"a parent process that failed to call `wait()`/`waitpid()`. "
                        f"Check the parent process or restart the orphaned service."
                    )

            # Failed services with status-only check
            if pkg.evidence_name == "Service Status" and is_service_status:
                failed_svcs = (
                    pkg.data.get("failed") or
                    pkg.data.get("failed_services") or
                    []
                )
                if isinstance(failed_svcs, list) and failed_svcs:
                    f_list = [str(s) for s in failed_svcs[:10]]
                    summary = ", ".join(f_list)
                    if len(failed_svcs) > 10:
                        summary += f" (+{len(failed_svcs) - 10} more)"
                    return (
                        f"## Failed Services\n\n"
                        f"The following **{len(failed_svcs)} service{'s' if len(failed_svcs) > 1 else ''}** "
                        f"{'are' if len(failed_svcs) > 1 else 'is'} in a failed state: {summary}\n\n"
                        f"Use `systemctl status <service>` or `journalctl -u <service>` "
                        f"for detailed error logs."
                    )

                # No failed services found
                all_svcs = pkg.data.get("services") or pkg.data.get("service_list") or []
                total = pkg.data.get("total") or pkg.data.get("service_count") or len(all_svcs)
                return (
                    f"## Service Status\n\n"
                    f"All **{total} services** are running normally. "
                    f"No failed or degraded services detected."
                )

        return None

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

    def _build_grafana_links(
        self,
        investigation: InvestigationRequest,
        user_request: str,
    ) -> str:
        """Build Grafana panel URLs from collected dashboard evidence."""
        from src.shared.secrets import get_tool_config

        config = get_tool_config("grafana")
        if not config:
            return ""

        grafana_url = config.get("url", "").rstrip("/")
        if not grafana_url:
            return ""

        dashboards = []
        query_params = {}
        for pkg in investigation.evidence:
            if not pkg.success:
                continue
            # Collect dashboard UIDs from evidence data.
            if pkg.evidence_name in ("Dashboards", "Dashboard Discovery"):
                data = pkg.data
                if isinstance(data, dict):
                    items = data.get("dashboards") or data.get("items") or []
                    if isinstance(items, list):
                        for item in items[:5]:
                            if isinstance(item, dict):
                                uid = item.get("uid") or ""
                                title = item.get("title") or item.get("name") or "Dashboard"
                                if uid:
                                    dashboards.append((title, uid))
                    raw_params = data.get("query_params") or {}
                    if isinstance(raw_params, dict):
                        query_params.update(raw_params)
        if not dashboards:
            return ""

        raw = user_request.lower()
        is_cpu = "cpu" in raw
        is_mem = any(kw in raw for kw in ("memory", "ram"))
        is_net = any(kw in raw for kw in ("network", "traffic"))
        is_disk = any(kw in raw for kw in ("disk", "storage"))

        from urllib import parse
        lines = ["**Grafana Dashboards:**"]
        for title, uid in dashboards:
            base_url = f"{grafana_url}/d/{uid}"
            params = {}
            if is_cpu:
                params["var-signal"] = "CPU"
            elif is_mem:
                params["var-signal"] = "Memory"
            elif is_net:
                params["var-signal"] = "Network"
            elif is_disk:
                params["var-signal"] = "Disk"

            raw_params = query_params
            if isinstance(raw_params, dict):
                params.update(raw_params)

            qs = parse.urlencode(params) if params else ""
            url = f"{base_url}?{qs}" if qs else base_url
            lines.append(f"- [{title}]({url})")

        return "\n".join(lines)
