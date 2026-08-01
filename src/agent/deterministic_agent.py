from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent.conversation_store import ConversationStoreProtocol

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
from src.pipeline.normalizer import Normalizer
from src.pipeline.target_resolver import UnknownTargetError
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
        conversation_store: ConversationStoreProtocol | None = None,  # type: ignore[valid-type]
        evidence_cache: object = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._assessment_model = assessment_model
        self._assessment_adapter = AssessmentAdapter()
        self._deterministic_responder = DeterministicResponder()
        self._conversation_store = conversation_store
        self._evidence_cache = evidence_cache
        if self._conversation_store:
            self._conversation_store.set_summarize_fn(self._assessment_model.assess_raw)

    @property
    def assessment_model(self) -> AssessmentModelAdapter:
        """Read-only access to the assessment model adapter."""
        return self._assessment_model

    def health_check(self, timeout: float = 5.0) -> bool:
        """Check if the assessment model backend is reachable.

        Returns True if the model client responds, False otherwise.
        """
        try:
            return self._assessment_model.health_check(timeout=timeout)
        except Exception:
            return False

    @property
    def conversation_store(self) -> ConversationStoreProtocol | None:  # type: ignore[valid-type]
        """Read-only access to the conversation store."""
        return self._conversation_store

    @conversation_store.setter
    def conversation_store(self, store: ConversationStoreProtocol | None) -> None:  # type: ignore[valid-type]
        """Set the conversation store after initialization."""
        self._conversation_store = store
        if store:
            store.set_summarize_fn(self._assessment_model.assess_raw)

    def run(self, user_request: str) -> str:
        """Run a full deterministic investigation and return assessment.

        Args:
            user_request: The raw user request.

        Returns:
            Assessment string from the model.
        """
        if not self._should_pipeline(user_request):
            return self.chat(user_request)

        try:
            investigation = self._execution_engine.execute(user_request)
            return self._assess(user_request, investigation)
        except UnknownTargetError as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Unknown target, not falling back to chat",
            )
            return str(exc)
        except (ValueError, TypeError) as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed with an invalid value",
            )
            logging.getLogger("agent").error("Pipeline failed", exc_info=True)
            raise
        except Exception as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed, falling back to chat",
            )
            logging.getLogger("agent").error("Pipeline failed", exc_info=True)
            return self.chat(user_request)

    def run_with_steps(self, user_request: str) -> dict:
        """Run pipeline + assessment, return structured result with steps.

        Single entry point for CLI and web. Returns a dict with:
          - response: assessment text
          - steps: list of pipeline step dicts for UI display
          - investigation: the InvestigationRequest (for CLI /evidence etc.)
        """
        if not self._should_pipeline(user_request):
            return {
                "response": self.chat(user_request),
                "steps": [],
                "investigation": None,
            }

        try:
            investigation = self._execution_engine.execute(user_request)
            response = self._assess(user_request, investigation)
            steps = self._build_pipeline_steps(investigation)
            return {
                "response": response,
                "steps": steps,
                "investigation": investigation,
            }
        except UnknownTargetError as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Unknown target, not falling back to chat",
            )
            return {
                "response": str(exc),
                "steps": [],
                "investigation": None,
            }
        except (ValueError, TypeError) as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed, falling back to chat",
            )
            # Log full exception details with exc_info=True and re-raise
            logging.getLogger("agent").error("Pipeline failed", exc_info=True)
            raise
        except Exception as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed, falling back to chat",
            )
            return {
                "response": self.chat(user_request),
                "steps": [],
                "investigation": None,
            }

    def _build_pipeline_steps(self, investigation: InvestigationRequest) -> list[dict]:
        """Serialize pipeline stages into step dicts for UI."""
        steps: list[dict[str, Any]] = []

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
                "confidence": (
                    investigation.confidence.name if investigation.confidence else "N/A"
                ),
                "target": investigation.target or "localhost",
                "matched_keywords": (
                    list(investigation.matched_keywords)
                    if investigation.matched_keywords
                    else []
                ),
                "required_evidence": [e.name for e in investigation.required_evidence],
                "optional_evidence": [e.name for e in investigation.optional_evidence],
                "planned_capabilities": plan_steps,
            }
        )

        evidence_list: list[dict[str, Any]] = []
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
                    "execution_duration": (
                        round(getattr(metrics, "execution_duration", 0), 3)
                        if metrics
                        else 0
                    ),
                    "total_nodes": getattr(metrics, "total_nodes", 0) if metrics else 0,
                    "successful_nodes": (
                        getattr(metrics, "successful_nodes", 0) if metrics else 0
                    ),
                    "failed_nodes": (
                        getattr(metrics, "failed_nodes", 0) if metrics else 0
                    ),
                    "parallel_ratio": (
                        round(getattr(metrics, "parallel_ratio", 0), 2)
                        if metrics
                        else 0
                    ),
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
        # Phase 6: Answer-type routing — skip LLM for simple fact/list queries.
        from src.pipeline.answer_type import AnswerType

        answer_type = getattr(investigation, "answer_type", None)
        if answer_type is not None and answer_type != AnswerType.ASSESSMENT:
            deterministic = self._deterministic_responder.try_response(investigation)
            if deterministic is not None:
                if self._conversation_store:
                    self._conversation_store.add_turn(user_request, deterministic)
                return deterministic

        # Deterministic shortcuts: skip LLM if evidence is simple enough.
        deterministic = self._deterministic_responder.try_response(investigation)
        if deterministic is not None:
            if self._conversation_store:
                self._conversation_store.add_turn(user_request, deterministic)
            return deterministic

        assessment_request = self._assessment_adapter.build(investigation)

        if self._conversation_store:
            context = self._build_chat_context()
            if context:
                conv_prefix = f"--- Recent conversation context ---\n{context}\n\n--- Current request ---\n{assessment_request.raw_request}"
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

    def _should_pipeline(self, user_request: str) -> bool:
        """Determine if request should go through the investigation pipeline.

        Multi-tier routing:
        1. Code/script generation requests → chat (no pipeline)
        2. KNOWLEDGE_ASSESSMENT → chat (no pipeline)
        3. Conceptual questions (X là gì? / giải thích) → chat
        4. Conversational / yes-no questions → chat (no pipeline)
        5. HIGH/MEDIUM confidence infrastructure intent → pipeline
        6. LOW confidence or MACHINE_ASSESSMENT fallback → Tier-2 LLM classifier

        Returns:
            True if the request should go through the investigation pipeline.
        """
        from src.pipeline.intent_resolver import Confidence, Intent, IntentResolver

        # A5: Code/script generation requests should NOT go through pipeline.
        # "viết/tạo/generate/write + script/config/file" → chat only.
        if self._is_code_generation_request(user_request):
            return False

        # A14: Bare hostname/alias typed standalone should route to pipeline.
        # e.g., "srv01", "monitor123" — user wants to investigate that target.
        if self._is_bare_target_candidate(user_request):
            return True

        resolver = IntentResolver()
        request = resolver.resolve(user_request)

        # Knowledge questions go to chat.
        if request.intent == Intent.KNOWLEDGE_ASSESSMENT:
            return False

        # A7: Conceptual questions ("X là gì?", "giải thích X", "sự khác biệt")
        # should go to chat for definition/explanation, NOT through pipeline.
        if self._is_conceptual_question(user_request):
            return False

        # Conversational / yes-no questions with MACHINE_ASSESSMENT intent
        # go to chat. These match generic keywords (e.g. "server") but the
        # user is asking a clarification question, not requesting an assessment.
        # Specific intents (CPU_ASSESSMENT, MEMORY_ASSESSMENT, etc.) are
        # NOT blocked — "mem như thế nào?" should still go to pipeline.
        #
        # Exception: vague health-check questions with infrastructure keywords
        # should still go to pipeline (e.g. "có vấn đề gì không?", "có ổn không?").
        # These are genuine infrastructure requests, not casual conversation.
        if request.intent == Intent.MACHINE_ASSESSMENT and self._is_conversational(
            user_request, request
        ):
            if self._is_vague_health_check(user_request):
                return True
            return False

        # High/medium confidence infrastructure intents go to pipeline.
        if request.confidence in (Confidence.HIGH, Confidence.MEDIUM):
            return True

        # LOW confidence or MACHINE_ASSESSMENT fallback → ask classifier.
        is_infra, _ = self.classify(user_request)
        return is_infra

    # ------------------------------------------------------------------
    # Conversational config – loaded from unified OrionConfig.
    # ------------------------------------------------------------------
    _conv_loaded: bool = False
    _conv_vi_patterns: list[str] = []
    _conv_en_patterns: list[str] = []
    _conv_question_mark: bool = True
    _conv_equivalence_markers: list[str] = [" là ", " is ", "=", "->"]

    @classmethod
    def _ensure_conv_loaded(cls) -> None:
        """Lazy-load conversational patterns from unified OrionConfig."""
        if cls._conv_loaded:
            return
        cls._conv_loaded = True
        from src.shared.config import get_config

        config = get_config()
        cls._conv_vi_patterns = config.vi_patterns or cls._conv_vi_patterns
        cls._conv_en_patterns = config.en_patterns or cls._conv_en_patterns
        cls._conv_question_mark = config.conv_question_mark
        cls._conv_equivalence_markers = config.conv_equivalence_markers

    @classmethod
    def _is_conversational(
        cls,
        user_request: str,
        request: InvestigationRequest,
    ) -> bool:
        """Detect conversational / yes-no questions that should skip pipeline.

        Patterns load from config/conversational_patterns.yaml.
        Falls back to hardcoded defaults if config is missing.

        Returns True if the request looks like a clarification question
        rather than a request for infrastructure assessment.
        """
        cls._ensure_conv_loaded()
        lower = user_request.lower().strip()

        # Vietnamese yes-no / conversational patterns.
        for pat in cls._conv_vi_patterns:
            if pat in lower:
                return True

        # English conversational patterns.
        for pat in cls._conv_en_patterns:
            if pat in lower:
                return True

        # Question-mark patterns: "X is Y?" with MACHINE_ASSESSMENT only.
        if (
            cls._conv_question_mark
            and lower.endswith("?")
            and request.intent == Intent.MACHINE_ASSESSMENT
        ):
            return True

        # Patterns that look like clarification about identity/equivalence ("X là Y?").
        is_pattern = any(p in lower for p in cls._conv_equivalence_markers)
        if is_pattern:
            return True

        return False

    # ------------------------------------------------------------------
    # Vague health-check patterns — loaded from config/health_patterns.yaml
    # via OrionConfig.  Questions that look conversational but are genuine
    # infrastructure health-check requests.
    # ------------------------------------------------------------------
    _VAGUE_HEALTH_PATTERNS: list[str] | None = None

    @classmethod
    def _get_health_patterns(cls) -> list[str]:
        """Return health-check patterns from unified config (lazy load)."""
        if cls._VAGUE_HEALTH_PATTERNS is not None:
            return cls._VAGUE_HEALTH_PATTERNS
        from src.shared.config import get_config

        config = get_config()
        patterns = config.vague_health_patterns
        if patterns:
            cls._VAGUE_HEALTH_PATTERNS = patterns
        else:
            # Fallback defaults if health_patterns.yaml is missing
            cls._VAGUE_HEALTH_PATTERNS = [
                "có vấn đề gì không",
                "có lỗi gì không",
                "có ổn không",
                "hoạt động tốt không",
                "tình trạng thế nào",
                "đang gặp vấn đề",
                "có sao không",
                "có vấn đề",
                "ổn định không",
                "chạy tốt không",
                "any issues",
                "is it healthy",
                "is it ok",
                "is it stable",
                "any problems",
                "anything wrong",
                "health check",
                "status check",
            ]
        return cls._VAGUE_HEALTH_PATTERNS

    @classmethod
    def _is_vague_health_check(cls, user_request: str) -> bool:
        """Detect vague health-check questions that should go to pipeline."""
        lower = user_request.lower().strip()
        return any(pat in lower for pat in cls._get_health_patterns())

    @staticmethod
    def _is_code_generation_request(user_request: str) -> bool:
        """A5: Detect requests to write/generate/create code/scripts/configs.

        Orion currently does not support writing code — it should respond
        honestly rather than routing to the infrastructure pipeline.
        """
        lower = user_request.lower().strip()
        _code_verbs = frozenset(
            {
                "viết",
                "viết giúp",
                "tạo",
                "tạo giúp",
                "write",
                "generate",
                "create",
                "soạn",
                "soạn giúp",
                "code",
            }
        )
        _code_targets = frozenset(
            {
                "script",
                "kịch bản",
                "code",
                "mã",
                "config",
                "cấu hình",
                "file",
                "tệp",
                "template",
                "mẫu",
                "backup",
                "sao lưu",
                "function",
                "hàm",
            }
        )
        has_verb = any(v in lower for v in _code_verbs)
        has_target = any(t in lower for t in _code_targets)
        return has_verb and has_target

    @staticmethod
    def _is_bare_target_candidate(user_request: str) -> bool:
        """A14: Detect bare hostname/alias typed as the only content.

        e.g., "srv01", "monitor123", "serverabc" — user likely wants to
        investigate that target, not ask a chat question about it.
        """
        stripped = user_request.strip()
        # Only match when the entire request is a single word/hostname.
        if " " in stripped:
            return False
        if len(stripped) <= 1:
            return False
        # Must look like a technical name (not a common Vietnamese/English word).
        _common_words = frozenset(
            {
                "help",
                "hi",
                "hello",
                "chào",
                "hỗ",
                "trợ",
                "giúp",
                "đỡ",
                "ok",
                "thanks",
                "cảm",
                "ơn",
                "yes",
                "no",
                "bye",
                "tạm",
                "biệt",
            }
        )
        if stripped.lower() in _common_words:
            return False
        import re as _re

        # Must be alphanumeric with optional hyphens/underscores/dots.
        return bool(_re.match(r"^[a-z0-9][a-z0-9._-]*$", stripped, _re.IGNORECASE))

    @staticmethod
    def _is_conceptual_question(user_request: str) -> bool:
        """A7: Detect conceptual/definition questions that should NOT route to pipeline.

        "X là gì?" / "giải thích X" / "sự khác biệt giữa X và Y" should go to chat.
        "X hiện tại là gì/bao nhiêu" (asking for current VALUE) should route to pipeline.
        """
        lower = user_request.lower().strip()

        # Definition patterns: always chat.
        _definition_patterns = (
            " là gì",
            " nghĩa là gì",
            " định nghĩa",
            " giải thích",
            " what is ",
            " what does ",
            " what are ",
            " sự khác biệt",
            " khác nhau",
            " difference between",
        )
        if any(p in lower for p in _definition_patterns):
            # Exception: "X hiện tại là gì" / "X hiện tại là bao nhiêu"
            # asking for current VALUE → route to pipeline.
            _value_indicators = (
                "hiện tại là",
                "hiện là",
                "bây giờ là",
                "current",
                "currently",
                "now",
            )
            if any(p in lower for p in _value_indicators):
                return False
            return True

        return False

    def classify(self, user_request: str) -> tuple[bool, str | None]:
        """Classify whether a question is infrastructure-related.

        Two-tier approach:
        1. Keyword-based IntentResolver (fast, no model call).
           If confidence is HIGH or MEDIUM → infra = True.
        2. If confidence is LOW → ask the model directly (cheap classifier call).
           Model says 'yes' → infra = True, 'no' → infra = False.

        The LLM classifier is only invoked when concept confidence from
        the Normalizer is < 0.4 (i.e., truly ambiguous). CPU/RAM/Disk
        classification is always deterministic — LLM is never used for those.

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

        # Check Normalizer confidence before falling through to LLM.
        # Only invoke LLM for truly ambiguous (confidence < 0.4) queries.
        normalizer = Normalizer()
        semantic = normalizer.normalize(user_request)
        if semantic.confidence >= 0.4:
            # The Normalizer found reasonable concept + action.
            # Deterministic classification: ask infrastructure.
            return (True, None)

        # Tier 2: ask the model (only for truly ambiguous cases, < 0.4 confidence).
        # Light prompt: ~100 tokens, response is 1 word.
        classifier_prompt = (
            f"Classify: infrastructure or general?\nQ: {user_request[:200]}\nA:"
        )
        try:
            answer = self._assessment_model.assess_raw(classifier_prompt)
            answer_clean = answer.strip().lower()[:20]
            is_infra = answer_clean.startswith("infrastructure")
            if self._conversation_store:
                label = "infrastructure" if is_infra else "general"
                self._conversation_store.add_classifier_turn(user_request, label)
            return (is_infra, None)
        except Exception as exc:
            _warning(
                "agent",
                error=str(exc)[:80],
                message="Tier-2 LLM classification failed, falling back to general chat",
            )
            return (False, "chat")

    def chat(self, user_request: str) -> str:
        """Send a free-form chat message to the model without pipeline context.

        Args:
            user_request: The raw user message.

        Returns:
            The model's response string.
        """
        # Security guard: check for dangerous patterns in user input
        # before sending to the LLM. This covers the chat() path which
        # bypasses KnowledgeTool entirely.
        danger = self._check_chat_safety(user_request)
        if danger:
            return danger

        try:
            from src.model.protocol.prompt_builder_v2 import _detect_language
            from src.model.protocol.prompt_loader import PromptLoader

            lang = _detect_language(user_request)
            loader = PromptLoader()
            system = loader.render("chat_system.j2", language=lang)
            if self._conversation_store:
                context = self._build_chat_context()
                if context:
                    prompt = f"{context}\n\nUser: {user_request}\n\nAssistant:"
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

    @staticmethod
    def _check_chat_safety(user_request: str) -> str | None:
        """Check chat input for dangerous patterns before sending to LLM.

        This guard covers the chat() path which bypasses KnowledgeTool
        and sends raw user input directly to the model via assess_raw().
        It uses the same detection patterns as ParameterSafetyInspector
        to maintain consistent security coverage.

        Returns:
            An error message string if dangerous patterns are detected,
            or None if the input is safe.
        """
        import re

        dangerous_patterns = [
            (r"\$\(.*\)", "command substitution detected"),
            (r"`[^`]+`", "backtick command substitution detected"),
            (r"\.\./", "path traversal detected"),
            (r"\x00", "null byte injection detected"),
            (r"(?i)(\bDROP\b\s+\bTABLE\b)", "DROP TABLE statement detected"),
            (r"(?i)(\bDELETE\b\s+\bFROM\b)", "DELETE FROM statement detected"),
        ]

        for pattern, reason in dangerous_patterns:
            if re.search(pattern, user_request):
                return (
                    f"I cannot process this request because it contains "
                    f"potentially dangerous content ({reason}). "
                    f"Please rephrase your question."
                )

        # Check for excessively long single "words" (possible injection).
        # A legitimate Vietnamese sentence won't have >500-char tokens.
        tokens = user_request.split()
        if any(len(t) > 500 for t in tokens):
            return (
                "I cannot process this request because it contains "
                "an excessively long token that may indicate an injection attempt."
            )

        return None

    def _build_chat_context(self) -> str:
        """Build a bounded chat context from conversation history.

        Uses the stored summary if available, plus the last few recent turns.
        Prevents context window overflow from long conversation histories.
        """
        summary = self._conversation_store.summary if self._conversation_store else None
        raw_history = (
            self._conversation_store.history if self._conversation_store else []
        )

        parts: list[str] = []

        if summary:
            parts.append(f"Conversation summary: {summary}")

        # Keep only last N user+assistant pairs (skip system/summary messages).
        max_recent_pairs = 4
        recent: list[dict[str, str]] = []
        for m in reversed(raw_history):
            if m.get("role") not in ("user", "assistant"):
                continue
            # Skip classifier labels.
            content = m.get("content", "")
            if content.startswith("[classified as"):
                continue
            recent.append(m)
            # Count pairs: keep N user messages worth of context.
            user_count = sum(1 for r in recent if r.get("role") == "user")
            if user_count >= max_recent_pairs:
                break
        recent.reverse()

        # Truncate long assistant messages to prevent context blow-up.
        max_msg_len = 600
        for m in recent:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if len(content) > max_msg_len:
                content = content[:max_msg_len] + "..."
            parts.append(f"{role}: {content}")

        return "\n\n".join(parts)

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

        # Phase 6: Resolve time range for Grafana embed links.
        from src.pipeline.time_range_resolver import TimeRangeResolver

        tr_resolver = TimeRangeResolver()
        time_range = tr_resolver.resolve(user_request)

        for name in kt._registry.target_names():
            try:
                tool = kt._registry.get_tool(name)
                if isinstance(tool, Tool):
                    links = tool.build_links(
                        evidence_list, user_request, time_range=time_range
                    )
                    if links:
                        parts.append(links)
            except Exception:
                _warning("agent", message=f"failed to build links for tool {name}")
        return "\n\n".join(parts)
