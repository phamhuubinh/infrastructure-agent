from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent.conversation_store import ConversationStoreProtocol
    from src.pipeline.request_frame import RequestFrame

from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
    build_evidence_receipts,
)
from src.model.assessment_guard import apply_assessment_guards
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.output_sanitizer import (
    enforce_language_quality,
    sanitize_api_response,
    sanitize_model_output,
)
from src.model.protocol.prompt_builder_v2 import (
    _detect_language,
    _normalize_evidence,
    build_assessment_prompt,
)
from src.pipeline.answer_type import AnswerType
from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.basic_calculator import (
    calculate,
    calculate_supplied_text,
    format_value,
    looks_like_arithmetic,
)
from src.pipeline.clarification_responder import ClarificationResponder
from src.pipeline.config_validator import ConfigValidator
from src.pipeline.deterministic_responder import DeterministicResponder
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_trace import (
    AnswerStrategy,
    ExecutionTrace,
    LLMUsageReason,
    ResponseStrategy,
    StageStatus,
    StageTrace,
    now_ms,
)
from src.pipeline.external_verification import (
    ExternalEvidenceRelevance,
    ExternalVerificationExecutor,
    ExternalVerificationOutcome,
)
from src.pipeline.external_verification_policy import ExternalVerificationPolicy
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.multi_intent_planner import MultiIntentPlanner, StepKind
from src.pipeline.narrow_logic import evaluate_text
from src.pipeline.normalizer import Normalizer
from src.pipeline.provenance_responder import (
    ProvenanceAnswer,
    ProvenanceResponder,
)
from src.pipeline.repetition_detector import RepetitionDetector
from src.pipeline.request_decomposer import RequestDecomposer
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
)
from src.pipeline.response_budget import ResponseBudgetPolicy
from src.pipeline.routing_decision import (
    EvidenceStatus,
    RoutingClarificationError,
    RoutingDecision,
    RoutingStatus,
)
from src.pipeline.safety_policy import sensitive_refusal
from src.pipeline.source_constraints import (
    SourceConstraintUnavailableError,
    compute_comparison_status,
    missing_comparison_sources,
)
from src.pipeline.target_resolver import AmbiguousTargetError, UnknownTargetError
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
        claim_guard_enabled: bool = True,
        external_verifier: ExternalVerificationExecutor | None = None,
        general_agent_routing_enabled: bool = True,
    ) -> None:
        self._execution_engine = execution_engine
        self._assessment_model = assessment_model
        self._assessment_adapter = AssessmentAdapter()
        self._deterministic_responder = DeterministicResponder()
        self._clarification_responder = ClarificationResponder()
        self._conversation_store = conversation_store
        stored_context = getattr(conversation_store, "investigation_context", None)
        self._session_context = (
            stored_context
            if isinstance(stored_context, SessionInvestigationContext)
            else SessionInvestigationContext()
        )
        self._evidence_cache = evidence_cache
        self._claim_guard_enabled = claim_guard_enabled
        self._general_agent_routing_enabled = general_agent_routing_enabled
        self._external_verifier = external_verifier or ExternalVerificationExecutor(
            getattr(execution_engine, "knowledge_tool", None)
        )
        # GA2-C10: the runtime must construct and consume ordered plans for
        # true multi-intent requests, not merely have the planner available
        # as an untested helper (see _maybe_run_explain_then_inspect_plan).
        self._multi_intent_planner = MultiIntentPlanner()
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
        stored_context = getattr(store, "investigation_context", None)
        self._session_context = (
            stored_context
            if isinstance(stored_context, SessionInvestigationContext)
            else SessionInvestigationContext()
        )
        if store:
            store.set_summarize_fn(self._assessment_model.assess_raw)

    def run(self, user_request: str) -> str:
        """Run an investigation and apply the universal delivery boundary."""
        return self._finalize_user_visible(
            self._run_unfinalized(user_request), user_request
        )

    def _run_unfinalized(self, user_request: str) -> str:
        """Run a full deterministic investigation and return assessment.

        Args:
            user_request: The raw user request.

        Returns:
            Assessment string from the model.
        """
        arithmetic = self._arithmetic_response(user_request)
        if arithmetic is not None:
            return arithmetic
        logic = self._logic_response(user_request)
        if logic is not None:
            return logic
        provenance = self._provenance_response(user_request)
        if provenance is not None:
            return provenance
        reset_response = self._reset_context_response(user_request)
        if reset_response is not None:
            return reset_response
        decision = self._route_request(user_request)
        if decision.status is RoutingStatus.GENERAL_CHAT:
            return self.chat(user_request)
        if decision.status is RoutingStatus.EXTERNAL_VERIFICATION:
            return self._run_external_verification(user_request, decision)
        if decision.status in {
            RoutingStatus.CLARIFICATION_REQUIRED,
            RoutingStatus.UNSUPPORTED,
        }:
            return self._clarification_responder.respond(decision)

        try:
            investigation = self._execution_engine.execute(decision.request_frame)
            self._remember_investigation(investigation)
            return self._assess(user_request, investigation)
        except RoutingClarificationError as exc:
            return self._clarification_responder.respond(exc.decision)
        except AmbiguousTargetError as exc:
            return self._clarification_responder.respond(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=decision.request_frame,
                    reason=str(exc),
                    missing_field="target",
                    candidates=exc.candidates,
                )
            )
        except UnknownTargetError as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Unknown target, not falling back to chat",
            )
            return self._clarification_responder.respond(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=decision.request_frame,
                    reason=str(exc),
                    missing_field="target",
                    candidates=tuple(exc.available),
                )
            )
        except SourceConstraintUnavailableError as exc:
            _warning("agent", error=str(exc)[:200], message="Source unavailable")
            return self._source_constraint_unavailable_response(exc)
        except (ValueError, TypeError) as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed with an invalid value",
            )
            logging.getLogger("agent").error("Pipeline failed", exc_info=True)
            raise
        except Exception as exc:
            _warning("agent", error=str(exc)[:200], message="Pipeline failed")
            logging.getLogger("agent").error("Pipeline failed", exc_info=True)
            return (
                "Không thể hoàn tất điều tra deterministic do lỗi pipeline. "
                "Không có model hoặc lệnh bổ sung nào được chạy."
            )

    def run_with_steps(self, user_request: str) -> dict:
        """Run with trace metadata and finalize the one visible response field."""
        result = self._run_with_steps_unfinalized(user_request)
        result["response"] = self._finalize_user_visible(
            result["response"], user_request
        )
        trace = result.get("execution_trace")
        if isinstance(trace, dict):
            strategy_name = trace.get("response_strategy")
            strategy = (
                ResponseStrategy[strategy_name]
                if isinstance(strategy_name, str)
                and strategy_name in ResponseStrategy.__members__
                else ResponseStrategy.GENERAL_EXPLANATION
            )
            budget = ResponseBudgetPolicy.for_strategy(strategy)
            text = result["response"]
            trace["response_metrics"] = {
                "character_count": len(text),
                "byte_count": len(text.encode("utf-8")),
                "estimated_output_tokens": ResponseBudgetPolicy.estimated_tokens(text),
                "input_tokens": None,
                "budget_class": budget.budget_class,
                "max_output_tokens": budget.max_output_tokens,
            }
        return result

    def _run_with_steps_unfinalized(self, user_request: str) -> dict:
        """Run pipeline + assessment, return structured result with steps.

        Single entry point for CLI and web. Returns a dict with:
          - response: assessment text
          - steps: list of pipeline step dicts for UI display
          - investigation: the InvestigationRequest (for CLI /evidence etc.)
          - trace_id: unique id of this request's ExecutionTrace
          - execution_trace: serialized ExecutionTrace (stage-level observability)
        """
        arithmetic = self._arithmetic_response(user_request)
        if arithmetic is not None:
            frame = (
                Normalizer()
                .normalize(user_request)
                .evolve(routing_status=RoutingStatus.RESOLVED)
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=AnswerStrategy.DETERMINISTIC_TEMPLATE,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.RESOLVED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.SELF_CONTAINED_REASONING,
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {
                "response": arithmetic,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        logic = self._logic_response(user_request)
        if logic is not None:
            frame = Normalizer().normalize(user_request).evolve(
                routing_status=RoutingStatus.RESOLVED
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=AnswerStrategy.DETERMINISTIC_TEMPLATE,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.RESOLVED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.SELF_CONTAINED_REASONING,
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {"response": logic, "steps": [], "investigation": None, "trace_id": trace.trace_id, "execution_trace": trace.to_dict()}
        provenance = self._provenance_response(user_request)
        if provenance is not None:
            frame = (
                Normalizer()
                .normalize(user_request)
                .evolve(routing_status=RoutingStatus.RESOLVED)
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=AnswerStrategy.DETERMINISTIC_TEMPLATE,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.RESOLVED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.PROVENANCE,
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {
                "response": provenance,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        reset_response = self._reset_context_response(user_request)
        if reset_response is not None:
            frame = (
                Normalizer()
                .normalize(user_request)
                .evolve(routing_status=RoutingStatus.RESOLVED)
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=AnswerStrategy.DETERMINISTIC_TEMPLATE,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.RESOLVED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.GENERAL_EXPLANATION,
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {
                "response": reset_response,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        # GA2-D08: EXPLAIN_PREVIOUS must explain the previous resolved
        # answer/evidence, never a newly invented environment request, and
        # must never rerun collectors unless the user explicitly asks for a
        # refresh. Intercept before any routing/pipeline decision, exactly
        # like the provenance/reset checks above.
        explain_previous = self._explain_previous_response(user_request)
        if explain_previous is not None:
            frame = (
                Normalizer()
                .normalize(user_request)
                .evolve(routing_status=RoutingStatus.RESOLVED)
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=AnswerStrategy.LLM_ASSESSMENT,
                llm_usage_reason=LLMUsageReason.EXPECTED_ASSESSMENT,
                routing_status=RoutingStatus.RESOLVED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.GENERAL_EXPLANATION,
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {
                "response": explain_previous,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        # GA2-C10: consume MultiIntentPlanner's ordered plan for a sequenced
        # compound request *before* the single-shot routing decision below,
        # or a request such as "Giải thích RAM là gì rồi kiểm tra RAM trên
        # monitor." collapses into whichever branch the last-mentioned
        # concept happens to match (previously: pure GENERAL_CHAT on the
        # trailing "là gì" cue) and the live-inspection half is silently
        # dropped rather than executed. Every other plan shape (e.g.
        # EXTERNAL-then-GENERATE) returns None here and falls through
        # unchanged: RoutingStatus.EXTERNAL_VERIFICATION below already
        # executes that pattern correctly end-to-end.
        plan_result = self._maybe_run_explain_then_inspect_plan(user_request)
        if plan_result is not None:
            return plan_result
        decision = self._route_request(user_request)
        if decision.status is RoutingStatus.GENERAL_CHAT:
            response, validation = self._chat_response(user_request)
            frame = decision.request_frame
            trace = ExecutionTrace(
                user_request=user_request,
                stages=self._artifact_validation_stage(validation),
                answer_strategy=AnswerStrategy.CHAT,
                llm_usage_reason=LLMUsageReason.EXPECTED_ASSESSMENT,
                routing_status=RoutingStatus.GENERAL_CHAT,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=self._general_response_strategy(user_request),
                request_class=frame.answer_type,
                actual_request_frame=frame.to_dict(),
            )
            return {
                "response": response,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        if decision.status is RoutingStatus.EXTERNAL_VERIFICATION:
            outcome = self._external_verifier.collect(
                decision.request_frame,
                user_request,
            )
            response = self._respond_external_verification(
                user_request,
                decision,
                outcome,
            )
            trace = ExecutionTrace(
                user_request=user_request,
                stages={
                    "external_verification": StageTrace(
                        name="external_verification",
                        status=(
                            StageStatus.SUCCEEDED
                            if outcome.verified
                            else StageStatus.FAILED
                        ),
                        message=(
                            "external evidence collected"
                            if outcome.verified
                            else (
                                outcome.failures[0]
                                if outcome.failures
                                else "unavailable"
                            )
                        ),
                    )
                },
                answer_strategy=(
                    AnswerStrategy.LLM_ASSESSMENT
                    if outcome.verified
                    else AnswerStrategy.DETERMINISTIC_TEMPLATE
                ),
                llm_usage_reason=(
                    LLMUsageReason.EXPECTED_ASSESSMENT
                    if outcome.verified
                    else LLMUsageReason.NONE
                ),
                routing_status=RoutingStatus.EXTERNAL_VERIFICATION,
                evidence_status=(
                    EvidenceStatus.PARTIAL
                    if outcome.partial
                    else (
                        EvidenceStatus.SUFFICIENT
                        if outcome.verified
                        else EvidenceStatus.UNAVAILABLE
                    )
                ),
                request_class=decision.request_frame.answer_type,
                response_strategy=ResponseStrategy.EXTERNAL_VERIFICATION,
                actual_request_frame=decision.request_frame.to_dict(),
                runtime_metrics={
                    "external_search_calls": outcome.search_calls,
                    "external_fetch_calls": outcome.fetch_calls,
                    "external_cache_hits": outcome.cache_hits,
                    "external_bytes": outcome.total_bytes,
                    "external_elapsed_ms": round(outcome.elapsed_ms, 3),
                },
            )
            return {
                "response": response,
                "steps": self._build_external_steps(outcome),
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }

        if decision.status in {
            RoutingStatus.CLARIFICATION_REQUIRED,
            RoutingStatus.UNSUPPORTED,
        }:
            if decision.status is RoutingStatus.CLARIFICATION_REQUIRED:
                self._remember_clarification(
                    decision.request_frame, decision.missing_field
                )
            strategy = (
                AnswerStrategy.CLARIFICATION
                if decision.status is RoutingStatus.CLARIFICATION_REQUIRED
                else AnswerStrategy.REFUSAL
            )
            trace = ExecutionTrace(
                user_request=user_request,
                answer_strategy=strategy,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=decision.status,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.CLARIFICATION_REFUSAL,
                request_class=decision.request_frame.answer_type,
                actual_request_frame=decision.request_frame.to_dict(),
            )
            return {
                "response": self._clarification_responder.respond(decision),
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }

        t0 = now_ms()
        strategy_out: list[str] = []
        try:
            investigation = self._execution_engine.execute(decision.request_frame)
            self._remember_investigation(investigation)
            response = self._assess(
                user_request, investigation, _strategy_out=strategy_out
            )
            steps = self._build_pipeline_steps(investigation)
            trace = self._build_execution_trace(
                investigation,
                strategy_out=strategy_out,
                total_duration_ms=now_ms() - t0,
            )
            return {
                "response": response,
                "steps": steps,
                "investigation": investigation,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        except RoutingClarificationError as exc:
            self._remember_clarification(
                exc.decision.request_frame, exc.decision.missing_field
            )
            trace = ExecutionTrace(
                user_request=user_request,
                failure_stage="routing",
                failure_reason=exc.decision.reason,
                answer_strategy=AnswerStrategy.CLARIFICATION,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.CLARIFICATION_REQUIRED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.CLARIFICATION_REFUSAL,
                request_class=exc.decision.request_frame.answer_type,
                actual_request_frame=exc.decision.request_frame.to_dict(),
                total_duration_ms=now_ms() - t0,
            )
            return {
                "response": self._clarification_responder.respond(exc.decision),
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        except (UnknownTargetError, AmbiguousTargetError) as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Unknown target, not falling back to chat",
            )
            candidates = (
                exc.candidates
                if isinstance(exc, AmbiguousTargetError)
                else tuple(exc.available)
            )
            target_decision = RoutingDecision(
                status=RoutingStatus.CLARIFICATION_REQUIRED,
                request_frame=decision.request_frame,
                reason=str(exc),
                missing_field="target",
                candidates=tuple(candidates),
            )
            self._remember_clarification(decision.request_frame, "target")
            trace = ExecutionTrace(
                user_request=user_request,
                failure_stage="target",
                failure_reason=str(exc)[:500],
                answer_strategy=AnswerStrategy.CLARIFICATION,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.CLARIFICATION_REQUIRED,
                evidence_status=EvidenceStatus.NOT_APPLICABLE,
                response_strategy=ResponseStrategy.CLARIFICATION_REFUSAL,
                request_class=decision.request_frame.answer_type,
                actual_request_frame=decision.request_frame.to_dict(),
                total_duration_ms=now_ms() - t0,
            )
            return {
                "response": self._clarification_responder.respond(target_decision),
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        except SourceConstraintUnavailableError as exc:
            trace = ExecutionTrace(
                user_request=user_request,
                failure_stage="source",
                failure_reason=str(exc)[:500],
                answer_strategy=AnswerStrategy.DETERMINISTIC_TEMPLATE,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.SOURCE_UNAVAILABLE,
                evidence_status=EvidenceStatus.UNAVAILABLE,
                response_strategy=ResponseStrategy.CLARIFICATION_REFUSAL,
                request_class=decision.request_frame.answer_type,
                actual_request_frame=decision.request_frame.to_dict(),
                total_duration_ms=now_ms() - t0,
            )
            return {
                "response": self._source_constraint_unavailable_response(exc),
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }
        except (ValueError, TypeError) as exc:
            _warning(
                "agent",
                error=str(exc)[:200],
                message="Pipeline failed without model fallback",
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
            trace = ExecutionTrace(
                user_request=user_request,
                failure_stage="pipeline",
                failure_reason=str(exc)[:500],
                answer_strategy=AnswerStrategy.REFUSAL,
                llm_usage_reason=LLMUsageReason.NONE,
                routing_status=RoutingStatus.FALLBACK,
                evidence_status=EvidenceStatus.UNAVAILABLE,
                response_strategy=ResponseStrategy.CLARIFICATION_REFUSAL,
                request_class=decision.request_frame.answer_type,
                actual_request_frame=decision.request_frame.to_dict(),
                total_duration_ms=now_ms() - t0,
            )
            response = (
                "Không thể hoàn tất điều tra deterministic do lỗi pipeline. "
                "Không có model hoặc lệnh bổ sung nào được chạy."
            )
            return {
                "response": response,
                "steps": [],
                "investigation": None,
                "trace_id": trace.trace_id,
                "execution_trace": trace.to_dict(),
            }

    def _arithmetic_response(self, user_request: str) -> str | None:
        """GA2-H04: deterministic answer for pure self-contained arithmetic."""
        cleaned = user_request.strip()
        supplied = calculate_supplied_text(cleaned)
        if supplied.recognized:
            result = supplied.result
        elif looks_like_arithmetic(cleaned):
            result = calculate(cleaned)
        else:
            return None
        if not result.ok or result.value is None:
            return "Không đủ dữ liệu để tính toán an toàn."
        lang = _detect_language(user_request)
        value = format_value(result.value)
        suffix = f" {supplied.unit}" if supplied.recognized and supplied.unit else ""
        if lang == "en":
            return f"Result: {value}{suffix}"
        return f"Kết quả: {value}{suffix}"

    @staticmethod
    def _logic_response(user_request: str) -> str | None:
        outcome = evaluate_text(user_request)
        return outcome.value if outcome is not None else None

    def _provenance_response(self, user_request: str) -> str | None:
        """GA2-E08: answer provenance questions from what was *actually*
        used (evidence receipts from the previous investigation), never
        just the user's requested source constraint — a normal request
        with no hard source constraint still actually used some real
        source, and that is what a provenance question asks about.

        Falls back to ``active_sources`` only when there are no receipts
        yet this session (nothing has actually been investigated), so an
        early provenance question still gets a sensible, honest answer
        instead of silently reporting nothing.
        """
        if not ProvenanceResponder.is_provenance_question(user_request):
            return None
        lang = _detect_language(user_request)
        receipts = self._session_context.previous_evidence_receipts
        if receipts:
            # Most-recent receipts (the last investigation) answer "what was
            # *just* used" — receipts are stored oldest-first, most-recent-last.
            last_timestamp = receipts[-1].timestamp
            latest = tuple(r for r in receipts if r.timestamp == last_timestamp)
            source_labels = {
                "linux": "Linux",
                "ssh": "SSH",
                "grafana": "Grafana",
                "zabbix": "Zabbix",
                "internet": "Internet",
            }
            sources = tuple(
                dict.fromkeys(
                    source_labels.get(r.source.casefold(), r.source.capitalize())
                    for r in latest
                    if r.source
                )
            )
            target = latest[0].target or self._session_context.active_target
            answer = ProvenanceAnswer(
                sources=sources,
                target=target,
                concepts=(
                    (self._session_context.active_concept,)
                    if self._session_context.active_concept
                    else ()
                ),
            )
        else:
            if self._session_context.last_evidence_status == "UNAVAILABLE":
                attempted = ProvenanceResponder.sources_from_constraints(
                    self._session_context.active_sources
                )
                attempted_text = ", ".join(attempted)
                if lang == "en":
                    return (
                        "No usable evidence was collected in the most recent "
                        f"investigation. Attempted/requested sources: {attempted_text or 'unknown'}."
                    )
                return (
                    "Không thu thập được bằng chứng dùng được trong lần điều tra gần nhất. "
                    f"Nguồn đã yêu cầu/thử: {attempted_text or 'không xác định'}."
                )
            sources = ProvenanceResponder.sources_from_constraints(
                self._session_context.active_sources
            )
            answer = ProvenanceAnswer(
                sources=sources,
                target=self._session_context.active_target,
                concepts=(
                    (self._session_context.active_concept,)
                    if self._session_context.active_concept
                    else ()
                ),
            )
        response = ProvenanceResponder().respond(answer, lang=lang)
        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)
        return response

    def _build_execution_trace(
        self,
        investigation: InvestigationRequest,
        *,
        strategy_out: list[str] | None = None,
        total_duration_ms: float | None = None,
    ) -> ExecutionTrace:
        """Build an ExecutionTrace for a completed investigation.

        ``strategy_out`` is an optional list populated by ``_assess`` with
        the answer strategy name actually used, so the trace reflects the
        real response path (deterministic responder vs LLM assessment).
        """
        strategy_name = strategy_out[0] if strategy_out else None
        answer_strategy = None
        if strategy_name:
            answer_strategy = AnswerStrategy[strategy_name]

        if answer_strategy == AnswerStrategy.LLM_ASSESSMENT:
            llm_reason = (
                LLMUsageReason.INSUFFICIENT_EVIDENCE
                if not investigation.evidence_complete
                else LLMUsageReason.EXPECTED_ASSESSMENT
            )
        else:
            llm_reason = LLMUsageReason.NONE

        investigation.answer_strategy = answer_strategy
        investigation.llm_usage_reason = llm_reason

        return ExecutionTrace.from_investigation(
            investigation,
            answer_strategy=answer_strategy,
            llm_usage_reason=llm_reason,
            response_strategy=self._live_response_strategy(investigation),
            total_duration_ms=total_duration_ms,
        )

    @staticmethod
    def _live_response_strategy(
        investigation: InvestigationRequest,
    ) -> ResponseStrategy:
        frame = investigation.request_frame
        constraints = getattr(frame, "source_constraints", ()) if frame else ()
        if len(constraints) >= 2:
            return ResponseStrategy.MULTI_SOURCE_COMPARISON
        return ResponseStrategy.LIVE_ENVIRONMENT

    @staticmethod
    def _general_response_strategy(user_request: str) -> ResponseStrategy:
        request = user_request.casefold()
        if any(marker in request for marker in ("translate", "dịch", "rewrite", "viết lại")):
            return ResponseStrategy.TRANSLATION_REWRITE
        if any(
            marker in request
            for marker in (
                "generate",
                "create",
                "write",
                "workflow",
                "yaml",
                "shell",
                "bash",
                "tạo",
                "viết",
            )
        ):
            return ResponseStrategy.ARTIFACT_GENERATION
        return ResponseStrategy.GENERAL_EXPLANATION

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
                    "status": pkg.capability_status.value,
                    "schema_version": pkg.schema_version,
                    "facts": [fact.to_dict() for fact in pkg.facts[:20]],
                    "collection_failures": list(pkg.collection_failures),
                    "source_links": list(pkg.source_links),
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

    def _assess(
        self,
        user_request: str,
        investigation: InvestigationRequest,
        _strategy_out: list[str] | None = None,
    ) -> str:
        # Phase 6: Answer-type routing — skip LLM for simple fact/list queries.
        def _record(strategy: str) -> None:
            if _strategy_out is not None:
                _strategy_out[:] = [strategy]
            investigation.answer_strategy = AnswerStrategy[strategy]

        # GA2-D08: RAW returns compact structured facts instead of
        # assessment prose for evidence-backed environment requests. Only
        # short-circuits when there are actual facts to show raw (see
        # _render_raw_facts); otherwise falls through so refusal/error
        # messaging from the normal path below still surfaces.
        if self._answer_shape_is_raw(user_request):
            raw_response = self._render_raw_facts(investigation)
            if raw_response is not None:
                _record(AnswerStrategy.DETERMINISTIC_FACT.name)
                if self._conversation_store:
                    self._conversation_store.add_turn(user_request, raw_response)
                return raw_response

        answer_type = getattr(investigation, "answer_type", None)
        if answer_type is not None and answer_type != AnswerType.ASSESSMENT:
            deterministic = self._deterministic_responder.try_response(investigation)
            if deterministic is not None:
                strategy = (
                    AnswerStrategy.DETERMINISTIC_FACT
                    if answer_type is AnswerType.FACT
                    else AnswerStrategy.DETERMINISTIC_TEMPLATE
                )
                _record(strategy.name)
                if self._conversation_store:
                    self._conversation_store.add_turn(user_request, deterministic)
                return deterministic

        # Deterministic shortcuts: skip LLM if evidence is simple enough.
        deterministic = self._deterministic_responder.try_response(investigation)
        if deterministic is not None:
            strategy = (
                AnswerStrategy.DETERMINISTIC_FACT
                if answer_type is AnswerType.FACT
                else AnswerStrategy.DETERMINISTIC_TEMPLATE
            )
            _record(strategy.name)
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
                    facts=assessment_request.facts,
                    collection_failures=assessment_request.collection_failures,
                    findings=assessment_request.findings,
                    health_summary=assessment_request.health_summary,
                    request_frame=assessment_request.request_frame,
                    unknowns=assessment_request.unknowns,
                    evidence_status=assessment_request.evidence_status,
                    allowed_claims=assessment_request.allowed_claims,
                )

        _record(AnswerStrategy.LLM_ASSESSMENT.name)
        investigation.llm_usage_reason = (
            LLMUsageReason.INSUFFICIENT_EVIDENCE
            if not investigation.evidence_complete
            else LLMUsageReason.EXPECTED_ASSESSMENT
        )
        response = self._assessment_model.assess(assessment_request)
        response = apply_assessment_guards(
            response,
            assessment_request,
            enable_claim_guard=self._claim_guard_enabled,
        )
        response = enforce_language_quality(
            sanitize_model_output(response), _detect_language(user_request)
        )
        if not response:
            response = "Không thể trả về nội dung đánh giá đó an toàn."

        # Append tool-specific deep links when available.
        links = self._build_tool_links(investigation, user_request)
        if links:
            response += "\n\n---\n\n" + links

        # GA2-E04: a multi-source comparison request must never silently
        # report as if every requested source was represented when one
        # actually failed/produced nothing — append an explicit note
        # naming the missing source(s) rather than leaving the reader to
        # infer completeness from prose alone.
        comparison_note = self._comparison_status_note(investigation)
        if comparison_note:
            response += f"\n\n{comparison_note}"

        response, validation = self._finalize_model_response(
            user_request,
            response,
            apply_short=self._answer_shape_is_short(user_request),
        )
        investigation.artifact_validation = validation

        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)

        return response

    def _answer_shape_is_short(self, user_request: str) -> bool:
        """GA2-D08: SHORT applies for this request or the session request."""
        current = SessionContextResolver.requested_answer_shape(user_request)
        if current == "SHORT":
            return True
        return (
            self._session_context.requested_answer_shape == "SHORT"
            and SessionContextResolver.is_follow_up_request(user_request)
        )

    def _answer_shape_is_raw(self, user_request: str) -> bool:
        """GA2-D08: RAW applies for this request or the session request."""
        current = SessionContextResolver.requested_answer_shape(user_request)
        if current == "RAW":
            return True
        return (
            self._session_context.requested_answer_shape == "RAW"
            and SessionContextResolver.is_follow_up_request(user_request)
        )

    @staticmethod
    def _apply_repetition_guard(response: str) -> str:
        """GA2-H12: pathological repetition/degeneration must never reach
        the user, at *every* path that returns model-generated text — not
        only the assessment path. This belongs at the shared final-output
        boundary alongside language/safety sanitation (which is why every
        call site here sits immediately after ``enforce_language_quality``).
        Recovers a useful non-repeated prefix when the detector can
        identify one; otherwise leaves the (already-bounded) text as is.
        """
        repetition = RepetitionDetector.detect(response)
        if repetition.pathological and repetition.recovered_text:
            return repetition.recovered_text
        return response

    def _finalize_model_response(
        self,
        user_request: str,
        response: str,
        *,
        apply_short: bool,
    ) -> tuple[str, dict[str, object] | None]:
        """Single model-output boundary before text becomes user-visible.

        Order is deliberate: strip hidden model text and language leakage,
        identify/validate artifacts, recover only prose repetition, then apply
        SHORT only to prose. Validation warnings are appended after any
        shortening, while code/config is exempt from prose repetition and
        shortening so its syntax and safety notice remain intact.
        """
        finalized = enforce_language_quality(
            sanitize_model_output(response), _detect_language(user_request)
        )
        if not finalized:
            finalized = "Không thể trả về nội dung đó an toàn."
        is_artifact = self._generated_artifact_candidate(user_request, finalized)
        if is_artifact is None:
            finalized = self._apply_repetition_guard(finalized)
            if apply_short:
                finalized = self._trim_to_short(finalized)
        return self._validate_generated_artifact(user_request, finalized)

    def _finalize_user_visible(self, response: str, user_request: str) -> str:
        """Universal final boundary for every public-agent response path.

        It has no model, tool, collector, or repair capability. Model paths
        have already performed artifact validation above; this final pass only
        applies the API-safe sanitizer to all early-return strategies and
        avoids prose repetition recovery for recognized generated artifacts.
        """
        visible = sanitize_api_response(response, user_request)
        if self._generated_artifact_candidate(user_request, visible) is not None:
            return visible
        return self._apply_repetition_guard(visible)

    @staticmethod
    def _artifact_validation_stage(
        validation: dict[str, object] | None,
    ) -> dict[str, StageTrace]:
        """Serialize only bounded validation facts into a safe trace stage."""
        if validation is None:
            return {}
        return {
            "artifact_validation": StageTrace(
                name="artifact_validation",
                status=(
                    StageStatus.SUCCEEDED
                    if validation["final_valid"]
                    else StageStatus.FAILED
                ),
                findings=list(validation["issues"]),
                message=(
                    f"{validation['artifact_type']}; "
                    f"initial_valid={validation['initial_valid']}; "
                    f"repair_attempted={validation['repair_attempted']}"
                ),
            )
        }

    @staticmethod
    def _generated_artifact_candidate(
        user_request: str, response: str
    ) -> tuple[str, str] | None:
        """Identify a supported *generated* artifact without executing it."""
        request = user_request.casefold()
        generation_words = (
            "generate",
            "create",
            "write",
            "produce",
            "provide",
            "tạo",
            "viet",
            "viết",
            "sinh",
            "cho tôi",
        )
        if not any(word in request for word in generation_words):
            return None

        fence = re.search(r"```(?P<lang>[a-zA-Z0-9_+-]*)\s*\n(?P<body>.*?)(?:```|\Z)", response, re.DOTALL)
        language = fence.group("lang").casefold() if fence else ""
        content = fence.group("body").rstrip() if fence else response
        github_request = any(
            marker in request
            for marker in ("github actions", "github action", "workflow", ".github/")
        )
        yaml_request = any(marker in request for marker in ("yaml", ".yml", ".yaml"))
        shell_request = any(
            marker in request
            for marker in ("shell", "bash", "sh script", "shell script", "script sh")
        )

        if github_request or (
            language in {"yaml", "yml"}
            and "jobs:" in content
            and ("runs-on:" in content or "uses:" in content)
        ):
            return "github_actions", content
        if language in {"yaml", "yml"} or yaml_request:
            return "yaml", content
        if language in {"sh", "shell", "bash", "zsh"} or shell_request:
            return "shell", content
        return None

    @classmethod
    def _validate_generated_artifact(
        cls, user_request: str, response: str
    ) -> tuple[str, dict[str, object] | None]:
        """Validate generated config content at the final delivery boundary.

        This deliberately performs parser/structural validation only. The
        returned metadata is bounded and excludes both prompts and artifact
        bodies, so it is safe for execution traces.
        """
        candidate = cls._generated_artifact_candidate(user_request, response)
        if candidate is None:
            return response, None
        artifact_type, content = candidate
        initial = ConfigValidator.validate(artifact_type, content)
        repaired = (
            ConfigValidator.safe_repair(artifact_type, content)
            if not initial.valid
            else None
        )
        repair_attempted = repaired is not None
        final = (
            ConfigValidator.validate(artifact_type, repaired)
            if repair_attempted
            else initial
        )
        issues = tuple(
            issue.message[:180] for issue in (initial.issues + final.issues)[:3]
        )
        metadata: dict[str, object] = {
            "artifact_type": artifact_type,
            "initial_valid": initial.valid,
            "repair_attempted": repair_attempted,
            "final_valid": final.valid,
            "issues": issues,
        }
        if final.valid:
            delivered = repaired if repair_attempted and repaired is not None else response
            warnings = tuple(
                issue.message[:180] for issue in final.issues if issue.kind == "warning"
            )
            if warnings:
                delivered = f"{delivered}\n\nValidation notice: {'; '.join(warnings)}"
            return (
                delivered,
                metadata,
            )
        summary = "; ".join(issues) or "validation failed"
        warning = (
            f"Validation warning: generated {artifact_type} was not validated "
            f"successfully ({summary}). It was not executed."
        )
        return f"{response}\n\n{warning}", metadata

    @staticmethod
    def _comparison_status_note(investigation: InvestigationRequest) -> str | None:
        """GA2-E04: explicit COMPLETE/PARTIAL/UNAVAILABLE note for a
        multi-source comparison request, naming exactly which requested
        source produced no evidence. Returns None for a non-comparison
        request (fewer than two concrete sources requested) or when every
        requested source is represented (no note needed for COMPLETE)."""
        frame = getattr(investigation, "request_frame", None)
        constraints = getattr(frame, "source_constraints", ()) if frame else ()
        fact_set = getattr(investigation, "fact_set", None)
        fact_sources = frozenset(
            fact.source for fact in (fact_set.facts if fact_set else ())
        )
        status = compute_comparison_status(constraints, fact_sources)
        if status in (None, "COMPLETE"):
            return None
        missing = missing_comparison_sources(constraints, fact_sources)
        missing_labels = ", ".join(constraint.name for constraint in missing)
        if status == "UNAVAILABLE":
            return (
                f"_So sánh không thực hiện được: không thu thập được dữ liệu "
                f"từ nguồn nào trong số đã yêu cầu ({missing_labels})._"
            )
        return (
            f"_So sánh chỉ một phần (PARTIAL): thiếu dữ liệu từ " f"{missing_labels}._"
        )

    @staticmethod
    def _render_raw_facts(investigation: InvestigationRequest) -> str | None:
        """GA2-D08: compact structured facts instead of assessment prose.

        For evidence-backed environment requests, RAW must return the
        collected facts directly rather than LLM-authored prose. This never
        bypasses source/target safety: it renders the *same* investigation
        that already went through the normal source/target-constrained
        pipeline (``_execution_engine.execute``) — it does not re-collect
        evidence differently or relax any constraint, it only changes how
        the already-resolved facts are presented.

        Returns ``None`` when there is nothing to show raw (e.g. collection
        failed or produced no facts), so the caller falls through to the
        normal deterministic/LLM response path and any refusal/error
        messaging still surfaces instead of an empty RAW response.
        """
        fact_set = getattr(investigation, "fact_set", None)
        facts = fact_set.facts if fact_set is not None else ()
        if not facts:
            return None
        lines = []
        for fact in facts:
            unit = f" {fact.unit}" if fact.unit else ""
            observed_at = (
                fact.observed_at.isoformat()
                if hasattr(fact.observed_at, "isoformat")
                else str(fact.observed_at)
            )
            lines.append(
                f"{fact.target}.{fact.metric} = {fact.value}{unit} "
                f"(source={fact.source}, observed_at={observed_at})"
            )
        return "\n".join(lines)

    _REFRESH_MARKERS = (
        "refresh",
        "kiểm tra lại",
        "kiem tra lai",
        "chạy lại",
        "chay lai",
        "cập nhật lại",
        "cap nhat lai",
        "check again",
        "run it again",
    )

    @classmethod
    def _is_explicit_refresh_request(cls, user_request: str) -> bool:
        """GA2-D08: EXPLAIN_PREVIOUS must not rerun collectors *unless* the
        user explicitly asks for a refresh."""
        lower = user_request.casefold()
        return any(marker in lower for marker in cls._REFRESH_MARKERS)

    def _last_assistant_response(self) -> str | None:
        """The most recent assistant turn, or None if there isn't one yet."""
        if not self._conversation_store:
            return None
        for turn in reversed(self._conversation_store.history):
            if isinstance(turn, dict) and turn.get("role") == "assistant":
                content = turn.get("content")
                return content if isinstance(content, str) else None
        return None

    def _explain_previous_response(self, user_request: str) -> str | None:
        """GA2-D08: EXPLAIN_PREVIOUS explains the previous resolved
        answer/evidence — never a newly invented environment request — and
        never reruns collectors unless the user explicitly asks for a
        refresh (``_is_explicit_refresh_request``, in which case this
        returns None so the normal pipeline runs as usual).
        """
        current = SessionContextResolver.requested_answer_shape(user_request)
        is_explain_previous = current == "EXPLAIN_PREVIOUS" or (
            self._session_context.requested_answer_shape == "EXPLAIN_PREVIOUS"
            and SessionContextResolver.is_follow_up_request(user_request)
        )
        if not is_explain_previous:
            return None
        if self._is_explicit_refresh_request(user_request):
            return None
        previous = self._last_assistant_response()
        if previous is None:
            response = (
                "Không có câu trả lời trước đó trong phiên này để giải thích thêm."
            )
        else:
            explain_prompt = (
                "Explain the previous answer below in more detail, in plain "
                "language. Do not invent new facts beyond what it already "
                "states, and do not describe running a new investigation.\n\n"
                f"Previous answer:\n{previous}"
            )
            # Route through chat() with conversation-store persistence
            # suppressed: chat() would otherwise persist this synthetic
            # explain_prompt as the "user" turn instead of the user's
            # actual short request ("explain more"/"giải thích thêm"),
            # corrupting history and downstream session-state tracking.
            store = self._conversation_store
            self._conversation_store = None
            try:
                response = self.chat(explain_prompt)
            finally:
                self._conversation_store = store
        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)
        return response

    @staticmethod
    def _trim_to_short(response: str) -> str:
        """Keep the substantive answer while dropping boilerplate sections.

        Refusal reasons, warnings, and provenance are non-removable: the trim
        only removes deep-link/reference trailers after a '---' separator and
        collapses extra blank lines.
        """
        if "---" in response:
            response = response.split("---", 1)[0].rstrip()
        return "\n".join(line for line in response.splitlines() if line.strip())

    def _is_knowledge_question(self, user_request: str) -> bool:
        """Check if the request is a general knowledge question (e.g. K8s)."""
        from src.pipeline.intent_resolver import IntentResolver as _Resolver

        _check = _Resolver()
        _req = _check.resolve(user_request)
        return _req.intent == Intent.KNOWLEDGE_ASSESSMENT

    def _should_pipeline(self, user_request: str) -> bool:
        """Compatibility wrapper around the canonical deterministic decision."""
        return self._route_request(user_request).resolved

    def _route_request(self, user_request: str) -> RoutingDecision:
        """Classify routing without invoking the assessment model."""
        from src.pipeline.intent_resolver import IntentResolver

        frame = SessionContextResolver().resolve(
            Normalizer().normalize(user_request), self._session_context
        )
        sensitive_reason = sensitive_refusal(user_request)
        if sensitive_reason is not None:
            return RoutingDecision(
                RoutingStatus.UNSUPPORTED,
                frame.evolve(routing_status=RoutingStatus.UNSUPPORTED),
                sensitive_reason,
            )
        decomposition = RequestDecomposer().decompose(frame)
        if decomposition.too_broad:
            return RoutingDecision(
                RoutingStatus.CLARIFICATION_REQUIRED,
                frame.evolve(routing_status=RoutingStatus.CLARIFICATION_REQUIRED),
                decomposition.reason,
                "concept",
                frame.concepts[:3],
            )
        if len(decomposition.subframes) > 1:
            frame = frame.evolve(subframes=decomposition.subframes)
        resolution = IntentResolver().resolve_frame(frame)
        frame = frame.evolve(
            intent_candidates=resolution.candidates,
            routing_status=resolution.routing_status,
        )

        external_policy = ExternalVerificationPolicy().decide(frame)
        if external_policy.requires_verification:
            return RoutingDecision(
                RoutingStatus.EXTERNAL_VERIFICATION,
                frame.evolve(routing_status=RoutingStatus.EXTERNAL_VERIFICATION),
                external_policy.reason,
            )

        # RequestFrame v2 carries deterministic semantics independent from
        # topic words.  This must run before AnswerType (for example,
        # "process và thread khác nhau" is a general comparison, not a
        # time-window comparison against the live environment).
        if (
            self._general_agent_routing_enabled
            and frame.execution_intent is ExecutionIntent.GENERATE_CONTENT
        ):
            return RoutingDecision(
                RoutingStatus.GENERAL_CHAT,
                frame.evolve(routing_status=RoutingStatus.GENERAL_CHAT),
                "content generation",
            )

        if (
            self._general_agent_routing_enabled
            and frame.execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT
        ):
            return RoutingDecision(
                RoutingStatus.UNSUPPORTED,
                frame.evolve(routing_status=RoutingStatus.UNSUPPORTED),
                "read-only boundary",
            )

        if (
            self._general_agent_routing_enabled
            and frame.request_domain is RequestDomain.GENERAL
        ):
            return RoutingDecision(
                RoutingStatus.GENERAL_CHAT,
                frame.evolve(routing_status=RoutingStatus.GENERAL_CHAT),
                "stable general knowledge",
            )

        # Keep the old fallback for callers that construct legacy frames
        # directly rather than going through Normalizer.
        if self._is_code_generation_request(user_request):
            return RoutingDecision(RoutingStatus.GENERAL_CHAT, frame, "code request")

        if frame.answer_type is AnswerType.ACTION:
            return RoutingDecision(
                RoutingStatus.UNSUPPORTED,
                frame.evolve(routing_status=RoutingStatus.UNSUPPORTED),
                "read-only boundary",
            )

        if (
            frame.answer_type is AnswerType.EXPLANATION
            or resolution.intent is Intent.KNOWLEDGE_ASSESSMENT
        ):
            return RoutingDecision(
                RoutingStatus.GENERAL_CHAT,
                frame.evolve(routing_status=RoutingStatus.GENERAL_CHAT),
                "general explanation",
            )

        lower = user_request.casefold().strip()
        general_patterns = (
            "hello",
            "xin chào",
            "cảm ơn",
            "thank",
            "bài thơ",
            "poem",
            "chính trị",
            "politics",
            "thời tiết",
            "weather",
            "bitcoin",
            "bạn là ai",
            "who are you",
            "công ty nào",
            "company are you",
        )
        if lower in {"hi", "hello", "chào", "thanks", "thank you"} or any(
            pattern in lower for pattern in general_patterns
        ):
            return RoutingDecision(
                RoutingStatus.GENERAL_CHAT,
                frame.evolve(routing_status=RoutingStatus.GENERAL_CHAT),
                "general chat",
            )

        # A bare technical name is an explicit target, even though it has no
        # concept words. TargetResolver will validate it before any collection.
        if self._is_bare_target_candidate(user_request):
            return RoutingDecision(
                RoutingStatus.RESOLVED,
                frame.evolve(routing_status=RoutingStatus.RESOLVED),
            )

        request = InvestigationRequest(
            raw_request=user_request,
            intent=resolution.intent,
        )
        if (
            resolution.intent is Intent.MACHINE_ASSESSMENT
            and frame.concepts == ("machine",)
            and self._is_conversational(user_request, request)
        ):
            if not self._is_vague_health_check(user_request):
                return RoutingDecision(
                    RoutingStatus.GENERAL_CHAT,
                    frame.evolve(routing_status=RoutingStatus.GENERAL_CHAT),
                    "conversational question",
                )

        if frame.answer_type is AnswerType.FORECAST and not frame.timeframe:
            return RoutingDecision(
                RoutingStatus.CLARIFICATION_REQUIRED,
                frame.evolve(routing_status=RoutingStatus.CLARIFICATION_REQUIRED),
                "forecast requires a bounded timeframe",
                "timeframe",
            )

        if frame.answer_type is AnswerType.COMPARISON and not frame.timeframe:
            return RoutingDecision(
                RoutingStatus.CLARIFICATION_REQUIRED,
                frame.evolve(routing_status=RoutingStatus.CLARIFICATION_REQUIRED),
                "comparison requires two bounded time windows",
                "timeframe",
            )

        params = frame.parameters
        service_name = getattr(params, "service_name", None)
        if (
            "service" in frame.concepts
            and service_name is None
            and any(
                marker in lower
                for marker in ("service kia", "service đó", "dịch vụ kia", "dịch vụ đó")
            )
        ):
            return RoutingDecision(
                RoutingStatus.CLARIFICATION_REQUIRED,
                frame.evolve(routing_status=RoutingStatus.CLARIFICATION_REQUIRED),
                "service reference has no bound name",
                "service",
            )

        if resolution.routing_status is RoutingStatus.CLARIFICATION_REQUIRED:
            candidates = tuple(
                candidate.intent.name for candidate in resolution.candidates[:3]
            )
            missing = frame.ambiguity[0] if frame.ambiguity else "concept"
            return RoutingDecision(
                RoutingStatus.CLARIFICATION_REQUIRED,
                frame.evolve(routing_status=RoutingStatus.CLARIFICATION_REQUIRED),
                resolution.reason,
                missing,
                candidates,
            )

        return RoutingDecision(
            RoutingStatus.RESOLVED,
            frame.evolve(routing_status=RoutingStatus.RESOLVED),
        )

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

    def _run_external_verification(
        self,
        user_request: str,
        decision: RoutingDecision,
    ) -> str:
        outcome = self._external_verifier.collect(decision.request_frame, user_request)
        return self._respond_external_verification(user_request, decision, outcome)

    def _respond_external_verification(
        self,
        user_request: str,
        decision: RoutingDecision,
        outcome: ExternalVerificationOutcome,
    ) -> str:
        """Assess collected web evidence or return an explicit UNKNOWN response.

        GA2-R1-B: Only promote to LLM assessment when there is SUFFICIENT
        relevant evidence.  PARTIAL or IRRELEVANT documents do NOT justify
        passing evidence to the model — concrete current claims (version,
        date, price, identity) must be grounded in SUFFICIENT evidence.
        """
        # Check for SUFFICIENT relevant evidence (not just "verified")
        has_sufficient = any(
            doc.relevance == ExternalEvidenceRelevance.SUFFICIENT
            for doc in outcome.documents
        )
        if not has_sufficient or outcome.evidence is None:
            return self._external_verification_unavailable_response(
                decision,
                outcome.failures[0] if outcome.failures else None,
            )
        evidence = outcome.evidence
        facts = evidence.facts
        request = AssessmentRequest(
            raw_request=user_request,
            intent="EXTERNAL_VERIFICATION",
            evidence=(evidence,),
            evidence_complete=not outcome.partial,
            missing_evidence=(("external-page-content",) if outcome.partial else ()),
            facts=facts,
            collection_failures=outcome.failures,
            request_frame=decision.request_frame.to_dict(),
            evidence_status=("PARTIAL" if outcome.partial else "SUFFICIENT"),
            allowed_claims=tuple(fact.id for fact in facts),
        )
        response = self._assessment_model.assess(request)
        response = apply_assessment_guards(
            response,
            request,
            enable_claim_guard=self._claim_guard_enabled,
        )
        sources = self._render_external_sources(outcome)
        if sources:
            response = f"{response}\n\n---\n\n{sources}"
        response = enforce_language_quality(
            sanitize_model_output(response), _detect_language(user_request)
        )
        if not response:
            response = "Không thể trả về nội dung đã kiểm chứng đó an toàn."
        # GA2-H12: pathological repetition must not reach the user here
        # either — this is a genuine model-generated response, same as
        # the assessment path.
        response, _ = self._finalize_model_response(
            user_request,
            response,
            apply_short=self._answer_shape_is_short(user_request),
        )
        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)
        return response

    @staticmethod
    def _external_verification_unavailable_response(
        decision: RoutingDecision,
        failure: str | None = None,
    ) -> str:
        """Honest deterministic fallback; never phrase model memory as current."""
        frame = decision.request_frame
        if frame.url_error:
            return f"Không thể kiểm chứng URL: {frame.url_error}"
        if "no-Internet" in (decision.reason or ""):
            return (
                "Không thể kiểm chứng thông tin bên ngoài vì yêu cầu này "
                "đồng thời cấm dùng Internet."
            )
        if frame.explicit_url:
            return (
                "Không thể đọc URL này ở thời điểm này. Không suy đoán nội dung "
                f"của URL. Lý do: {failure or 'không thu thập được external evidence.'}"
            )
        return (
            "Không thể kiểm chứng thông tin hiện tại từ Internet ở thời điểm "
            f"này: {failure or 'search provider chưa được cấu hình.'} Không dùng kiến thức "
            "model có thể đã cũ để trả lời như một thông tin đã được kiểm chứng."
        )

    @staticmethod
    def _render_external_sources(outcome: ExternalVerificationOutcome) -> str:
        if not outcome.documents:
            return ""
        lines = ["Nguồn đã kiểm chứng:"]
        for document in outcome.documents:
            timestamp = document.retrieved_at.isoformat()
            title = document.title.replace("\n", " ").strip()
            lines.append(f"- {title}: {document.url} (lấy lúc {timestamp})")
        if outcome.failures:
            lines.append(f"Giới hạn: {outcome.failures[0]}")
        return "\n".join(lines)

    @staticmethod
    def _build_external_steps(
        outcome: ExternalVerificationOutcome,
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "external_verification",
                "verified": outcome.verified,
                "partial": outcome.partial,
                "search_calls": outcome.search_calls,
                "fetch_calls": outcome.fetch_calls,
                "cache_hits": outcome.cache_hits,
                "total_bytes": outcome.total_bytes,
                "elapsed_ms": round(outcome.elapsed_ms, 3),
                "failures": list(outcome.failures),
                "sources": [
                    {
                        "title": document.title,
                        "url": document.url,
                        "provider": document.provider,
                        "retrieved_at": document.retrieved_at.isoformat(),
                        "truncated": document.truncated,
                        "content_status": document.content_status.value,
                    }
                    for document in outcome.documents
                ],
            }
        ]

    @staticmethod
    def _source_constraint_unavailable_response(
        error: SourceConstraintUnavailableError,
    ) -> str:
        return (
            "Không thể kiểm tra theo đúng ràng buộc nguồn đã yêu cầu: "
            f"{error} Không fallback sang nguồn khác."
        )

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

        This compatibility API delegates to deterministic routing. Ambiguous
        input returns ``(False, "clarification")`` and never invokes a model.

        Returns:
            (is_infra: bool, reason: str | None)
            reason is set to "chat" if classified as general chat.
        """
        decision = self._route_request(user_request)
        if decision.status is RoutingStatus.RESOLVED:
            return (True, None)
        if decision.status is RoutingStatus.CLARIFICATION_REQUIRED:
            return (False, "clarification")
        if decision.status is RoutingStatus.UNSUPPORTED:
            return (False, "unsupported")
        return (False, "chat")

    def chat(self, user_request: str) -> str:
        """Send a free-form chat message to the model without pipeline context.

        Args:
            user_request: The raw user message.

        Returns:
            The model's response string.
        """
        response, _ = self._chat_response(user_request)
        return self._finalize_user_visible(response, user_request)

    def _chat_response(self, user_request: str) -> tuple[str, dict[str, object] | None]:
        """Return chat output plus safe artifact-validation metadata."""
        # Security guard: check for dangerous patterns in user input
        # before sending to the LLM. This covers the chat() path which
        # bypasses KnowledgeTool entirely.
        danger = self._check_chat_safety(user_request)
        if danger:
            return danger, None

        try:
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

            response = enforce_language_quality(
                sanitize_model_output(self._assessment_model.assess_raw(prompt)), lang
            )
            if not response:
                return "Không thể trả về nội dung đó an toàn.", None
            # GA2-H12: chat() is a genuine model-generated response path too
            # (it bypasses the pipeline entirely via assess_raw()) — must
            # not be exempt from the repetition/degeneration guard.
            response, validation = self._finalize_model_response(
                user_request,
                response,
                apply_short=self._answer_shape_is_short(user_request),
            )
            if self._conversation_store:
                self._conversation_store.add_turn(user_request, response)
            return response, validation
        except Exception as exc:
            return f"Sorry, I couldn't process that: {exc}", None

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

        if sensitive_refusal(user_request) is not None:
            language = _detect_language(user_request)
            if language == "en":
                return (
                    "I cannot disclose hidden instructions, secrets, credentials, "
                    "or credential files."
                )
            return (
                "Tôi không thể tiết lộ hướng dẫn nội bộ, bí mật, thông tin "
                "đăng nhập hoặc tệp chứa thông tin xác thực."
            )

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

        # A chat request can discuss shell commands, but it cannot ask Orion to
        # execute a mutation.  This path has no tool access; rejecting explicit
        # imperatives also prevents the model from hallucinating an action
        # receipt for prompt-injection text.
        mutation_request = re.search(
            r"(?i)\b(run|execute|do|chạy|thực hiện|hãy|giúp tôi)\b.{0,80}"
            r"\b(rm|mv|chmod|chown|reboot|shutdown|kill|sudo|"
            r"systemctl\s+(?:start|stop|restart|enable|disable)|"
            r"apt(?:-get)?\s+(?:install|remove)|docker\s+(?:rm|stop|restart))\b",
            user_request,
        )
        if mutation_request:
            return (
                "Orion is read-only and did not execute that command or change "
                "the system. I can explain the command or suggest a safe, "
                "operator-reviewed procedure."
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
        decision = self._route_request(user_request)
        if not decision.resolved:
            raise RoutingClarificationError(decision)
        investigation = self._execution_engine.execute(decision.request_frame)
        self._remember_investigation(investigation)
        return investigation

    def _remember_clarification(
        self, frame: RequestFrame | None, missing_field: str | None
    ) -> None:
        """GA2-E02: persist whatever the partial frame already establishes
        (e.g. a hard source constraint from "Chỉ dùng Grafana...") *before*
        asking for clarification, and record which field is pending.

        Without this, every CLARIFICATION_REQUIRED return path skipped
        session-state persistence entirely (it has no InvestigationRequest
        to hand to ``_remember_investigation``), so a hard source
        restriction stated in the same turn as an unresolved target was
        silently lost — the next turn's bare clarification answer (e.g.
        "monitor.") resolved with no memory of "Grafana-only" at all.
        """
        if frame is None:
            return
        context = self._session_context.update_from_frame(frame)
        context = context.with_pending_clarification(missing_field)
        self._session_context = context
        setter = getattr(self._conversation_store, "set_investigation_context", None)
        if callable(setter):
            setter(context)

    def _remember_investigation(self, investigation: InvestigationRequest) -> None:
        """Persist resolved semantics, never raw evidence, for later routing."""
        frame = investigation.request_frame
        if frame is None:
            return
        context = self._session_context
        if (
            frame.target_resolved
            and context.active_target
            and frame.target_resolved != context.active_target
            and "target" not in frame.context_applied
        ):
            context = context.switch_target(frame.target_resolved)
        context = context.update_from_frame(frame)
        # GA2-E08: persist what was *actually* used (source/target/capability
        # per collected fact), independent of any hard source constraint the
        # user did or didn't state — this is what a provenance question must
        # answer from, not active_sources (the request-time constraint).
        fact_sources = frozenset(fact.source for fact in investigation.fact_set.facts)
        comparison_status = compute_comparison_status(
            frame.source_constraints, fact_sources
        )
        status = comparison_status or (
            "COMPLETE" if investigation.evidence_complete else "PARTIAL"
        )
        receipts = build_evidence_receipts(
            investigation.fact_set,
            status=status,
        )
        context = context.with_investigation_evidence(receipts, status=status)
        # GA2-D08: persist a confident answer-shape request into the session
        # for later response construction (never a tool/source decision).
        shape = SessionContextResolver.requested_answer_shape(frame.raw_request)
        if shape is not None:
            context = context.with_answer_shape(shape)
        # GA2-D07: persist a corrected concept so later turns inherit it.
        if SessionContextResolver.is_correction_request(frame.raw_request):
            corrected = SessionContextResolver.corrected_concept(frame.raw_request)
            if corrected is not None:
                context = context.with_corrected_concept(corrected)
        self._session_context = context
        setter = getattr(self._conversation_store, "set_investigation_context", None)
        if callable(setter):
            setter(context)

    def _reset_context_response(self, user_request: str) -> str | None:
        if not SessionContextResolver.is_reset_request(user_request):
            return None
        context = self._session_context.reset()
        self._session_context = context
        setter = getattr(self._conversation_store, "set_investigation_context", None)
        if callable(setter):
            setter(context)
        response = "Đã xóa ngữ cảnh điều tra đang hoạt động."
        if self._conversation_store:
            self._conversation_store.add_turn(user_request, response)
        return response

    def _maybe_run_explain_then_inspect_plan(self, user_request: str) -> dict | None:
        """GA2-C10: execute MultiIntentPlanner's EXPLAIN-then-INSPECT plan.

        Returns ``None`` (meaning: fall through to the normal single-shot
        routing path in ``run_with_steps``) unless ``user_request`` is a
        sequenced compound request whose first step is a stable-knowledge
        explanation and whose second step is a live environment read —
        e.g. "Giải thích RAM là gì rồi kiểm tra RAM trên monitor.". Any
        other plan shape (including EXTERNAL-then-GENERATE) is left to the
        existing ``RoutingStatus.EXTERNAL_VERIFICATION`` path, which
        already executes it correctly end-to-end.

        Each half is executed through the exact same deterministic
        machinery it would use standalone (``chat`` for the explanation,
        the full ``run_with_steps`` pipeline — including target/source
        resolution and all existing error handling — for the live read),
        never a free-form ReAct/tool-selection loop. Conversation-store
        persistence is deferred and done once here with the *original*
        compound request text, so history/session state reflect what the
        user actually asked rather than the two synthetic sub-clauses.
        """
        frame = SessionContextResolver().resolve(
            Normalizer().normalize(user_request), self._session_context
        )
        plan = self._multi_intent_planner.plan(frame)
        if plan is None or plan.steps[0].kind is not StepKind.EXPLAIN:
            return None
        clauses = self._multi_intent_planner.split_sequenced_clauses(user_request)
        if clauses is None:
            return None
        explain_request, inspect_request = clauses

        t0 = now_ms()
        store = self._conversation_store
        self._conversation_store = None
        try:
            explanation = self.chat(explain_request)
            inspect_result = self.run_with_steps(inspect_request)
        finally:
            self._conversation_store = store

        combined_response = f"{explanation}\n\n---\n\n{inspect_result['response']}"
        inspect_trace = inspect_result.get("execution_trace") or {}
        stages = {
            "step_1_explain": StageTrace(
                name="step_1_explain", status=StageStatus.SUCCEEDED
            ),
            "step_2_inspect": StageTrace(
                name="step_2_inspect",
                status=(
                    StageStatus.FAILED
                    if inspect_trace.get("failure_stage")
                    else StageStatus.SUCCEEDED
                ),
            ),
        }
        resolved_frame = frame.evolve(routing_status=RoutingStatus.RESOLVED)
        trace = ExecutionTrace(
            user_request=user_request,
            stages=stages,
            answer_strategy=AnswerStrategy.LLM_ASSESSMENT,
            llm_usage_reason=LLMUsageReason.EXPECTED_ASSESSMENT,
            routing_status=RoutingStatus.RESOLVED,
            evidence_status=(
                EvidenceStatus.SUFFICIENT
                if not inspect_trace.get("failure_stage")
                else EvidenceStatus.PARTIAL
            ),
            request_class=frame.answer_type,
            actual_request_frame=resolved_frame.to_dict(),
            total_duration_ms=now_ms() - t0,
            runtime_metrics={
                "plan_steps": len(plan.steps),
                "plan_source": plan.source,
            },
        )
        if self._conversation_store:
            setter = getattr(
                self._conversation_store, "set_investigation_context", None
            )
            if callable(setter):
                setter(self._session_context)
            self._conversation_store.add_turn(user_request, combined_response)
        return {
            "response": combined_response,
            "steps": [
                {
                    "type": "planned_step",
                    "order": 1,
                    "kind": "EXPLAIN",
                    "status": "SUCCEEDED",
                },
                *inspect_result.get("steps", []),
            ],
            "investigation": inspect_result.get("investigation"),
            "trace_id": trace.trace_id,
            "execution_trace": trace.to_dict(),
        }

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
        link_time_range = time_range.as_tuple() if time_range is not None else None

        for name in kt._registry.target_names():
            try:
                tool = kt._registry.get_tool(name)
                if isinstance(tool, Tool):
                    links = tool.build_links(
                        evidence_list, user_request, time_range=link_time_range
                    )
                    if links:
                        parts.append(links)
            except Exception:
                _warning("agent", message=f"failed to build links for tool {name}")
        return "\n\n".join(parts)
