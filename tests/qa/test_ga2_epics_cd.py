"""GA2-C07/C08/C10 + GA2-D07/D08/D09 deterministic regression coverage."""

from __future__ import annotations

from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.pipeline.multi_intent_planner import MultiIntentPlanner, StepKind
from src.pipeline.normalizer import Normalizer

# ---------------------------------------------------------------------------
# GA2-C08 — URL literal vs fetch intent
# ---------------------------------------------------------------------------


def test_url_literal_with_no_fetch_directive_is_not_a_fetch_instruction() -> None:
    """'đừng fetch URL' must win; URL is content, not an authorization."""
    frame = Normalizer().normalize(
        "Viết Dockerfile tải https://example.com/app.tar.gz nhưng đừng fetch URL."
    )
    assert frame.url_literal is True
    assert frame.explicit_url is None
    assert frame.request_domain.name == "CONTENT_GENERATION"
    assert frame.external_need.name == "NONE"


def test_url_fetch_request_keeps_explicit_url() -> None:
    frame = Normalizer().normalize("Đọc https://example.com và tóm tắt nội dung chính.")
    assert frame.url_literal is False
    assert frame.explicit_url == "https://example.com"
    assert frame.request_domain.name == "EXTERNAL_INFORMATION"


def test_relevant_english_no_fetch_directive() -> None:
    frame = Normalizer().normalize(
        "Write a config referencing https://example.com/app.tar.gz but do not fetch it."
    )
    assert frame.url_literal is True
    assert frame.explicit_url is None


# ---------------------------------------------------------------------------
# GA2-C07 — current information inside compound generation requests
# ---------------------------------------------------------------------------


def test_compound_generation_preserves_current_external_dependency() -> None:
    frame = Normalizer().normalize(
        "Tìm phiên bản Python mới nhất rồi viết Dockerfile dùng phiên bản đó."
    )
    assert frame.request_domain.name == "EXTERNAL_INFORMATION"
    assert frame.external_need.name == "REQUIRED"
    # The generation intent is preserved for the compound deliverable.
    assert frame.execution_intent.name == "GENERATE_CONTENT"
    assert frame.freshness_phrase == "mới nhất"


def test_plain_generation_without_current_dependency_stays_generation() -> None:
    frame = Normalizer().normalize(
        "Viết Dockerfile cài đặt Python và expose port 8000."
    )
    assert frame.request_domain.name == "CONTENT_GENERATION"
    assert frame.external_need.name == "NONE"


# ---------------------------------------------------------------------------
# GA2-C10 — ordered multi-intent planning
# ---------------------------------------------------------------------------


def test_explain_then_inspect_ordered_plan() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize(
        "Giải thích RAM là gì rồi kiểm tra RAM trên monitor."
    )
    plan = planner.plan(frame)
    assert plan is not None
    assert [step.kind for step in plan.steps] == [
        StepKind.EXPLAIN,
        StepKind.INSPECT,
    ]
    assert plan.steps[0].order == 1
    assert plan.steps[1].order == 2


def test_external_then_generate_preserves_dependency() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize(
        "Tìm phiên bản hiện tại rồi tạo config dùng phiên bản đó."
    )
    plan = planner.plan(frame)
    assert plan is not None
    assert plan.steps[1].kind is StepKind.GENERATE
    assert plan.steps[1].depends_on == (1,)


def test_comparison_is_not_treated_as_sequenced_plan() -> None:
    planner = MultiIntentPlanner()
    frame = Normalizer().normalize("So sánh CPU từ Grafana và Zabbix trên monitor.")
    assert planner.plan(frame) is None


# ---------------------------------------------------------------------------
# GA2-D07 — correction semantics
# ---------------------------------------------------------------------------


def test_correction_replaces_active_concept() -> None:
    # GA2-D07: exact-value assertions per the backlog's confirmed-failing
    # example. A test that merely accepts either CPU or RAM is not valid
    # coverage — "Không phải CPU" explicitly negates CPU, so only RAM is
    # the semantically correct correction.
    assert SessionContextResolver.is_correction_request("Không phải CPU, tôi hỏi RAM.") is True
    corrected = SessionContextResolver.corrected_concept("Không phải CPU, tôi hỏi RAM.")
    assert corrected == "ram"

    context = SessionInvestigationContext(active_concept="cpu")
    assert context.with_corrected_concept(corrected).active_concept == "ram"


def test_corrected_concept_handles_replacement_stated_before_negation() -> None:
    # GA2-D07: "Ý tôi là disk, không phải memory." states the replacement
    # (disk) first and negates memory afterwards — the negated concept is
    # not always the first one mentioned.
    assert (
        SessionContextResolver.corrected_concept("Ý tôi là disk, không phải memory.")
        == "disk"
    )


def test_corrected_concept_handles_english_negation() -> None:
    # GA2-D07: "Not CPU, memory." — English negation marker.
    assert SessionContextResolver.corrected_concept("Not CPU, memory.") == "memory"


def test_correction_does_not_union_concepts_in_resolver() -> None:
    ctx = SessionInvestigationContext(active_concept="memory")
    resolver = SessionContextResolver()
    frame = Normalizer().normalize("Không phải CPU, tôi hỏi RAM.")
    resolved = resolver.resolve(frame, ctx)
    # The corrected concept replaces the negated one; it never unions with
    # either the negated concept (cpu) or the unrelated prior active
    # concept (memory) — only the exact replacement (ram) is correct.
    assert resolved.concepts == ("ram",)
    assert "concept_correction" in resolved.context_applied


# ---------------------------------------------------------------------------
# GA2-D08 — requested answer shape
# ---------------------------------------------------------------------------


def test_answer_shape_detection() -> None:
    assert SessionContextResolver.requested_answer_shape("ngắn thôi") == "SHORT"
    assert SessionContextResolver.requested_answer_shape("short answer") == "SHORT"
    assert SessionContextResolver.requested_answer_shape("raw data only") == "RAW"
    assert (
        SessionContextResolver.requested_answer_shape("giải thích câu trước")
        == "EXPLAIN_PREVIOUS"
    )


def test_answer_shape_persists_in_semantic_state() -> None:
    ctx = SessionInvestigationContext().with_answer_shape("SHORT")
    assert ctx.requested_answer_shape == "SHORT"
    assert ctx.to_dict()["requested_answer_shape"] == "SHORT"
    assert SessionInvestigationContext.from_dict(
        ctx.to_dict()
    ).requested_answer_shape == ("SHORT")


# ---------------------------------------------------------------------------
# GA2-D09 — vague referents
# ---------------------------------------------------------------------------


def test_vague_referent_detection() -> None:
    assert SessionContextResolver.is_vague_referent("máy kia") is True
    assert SessionContextResolver.is_vague_referent("server đó") is True
    assert SessionContextResolver.is_vague_referent("server kia") is True
    assert (
        SessionContextResolver.is_vague_referent("Kiểm tra CPU trên monitor") is False
    )


def test_vague_referent_never_inherits_implicit_target() -> None:
    resolver = SessionContextResolver()
    ctx = SessionInvestigationContext(active_target="monitor", active_concept="cpu")
    frame = Normalizer().normalize("Máy kia có ổn không?")
    resolved = resolver.resolve(frame, ctx)
    # No implicit localhost/target guess for a vague referent.
    assert resolved.target_raw is None


# ---------------------------------------------------------------------------
# GA2-C10 — runtime integration (the agent must consume the plan, not just
# be able to construct one; see MultiIntentPlanner's own unit tests for the
# planner-only coverage).
# ---------------------------------------------------------------------------


def test_multi_intent_planner_is_actually_referenced_by_the_agent_runtime() -> None:
    """Source-level guard against the exact regression GA2-C10 reports:

    'the production runtime does not currently call MultiIntentPlanner;
    references are limited to the module/tests.' A future edit that removes
    the runtime wiring (leaving only the planner + its own unit tests)
    should fail this test rather than silently reintroducing the gap.
    """
    import inspect

    from src.agent import deterministic_agent

    source = inspect.getsource(deterministic_agent)
    assert "MultiIntentPlanner" in source
    assert "self._multi_intent_planner.plan(" in source


def test_agent_executes_both_halves_of_an_explain_then_inspect_plan() -> None:
    """GA2-C10 acceptance: a runtime-level test, not just a planner-object
    test. Before this integration, 'Giải thích RAM là gì rồi kiểm tra RAM.'
    routed as pure GENERAL_CHAT (matching only the trailing "là gì" cue)
    and the live-inspection half was never executed at all — the second
    step was silently dropped rather than executed or explicitly blocked.
    """
    from src.agent.runtime_factory import create_deterministic_agent
    from src.pipeline.target_resolver import TargetResolver

    original_resolve = TargetResolver.resolve

    def patched_resolve(self, request):
        request.target = "localhost"

    TargetResolver.resolve = patched_resolve
    try:
        agent = create_deterministic_agent()
        result = agent.run_with_steps("Giải thích RAM là gì rồi kiểm tra RAM.")
    finally:
        TargetResolver.resolve = original_resolve

    # Both halves actually ran: the combined response carries content from
    # each step (a "---" separator between them), not just the explanation.
    assert "---" in result["response"]
    # The live-inspection half genuinely executed the pipeline (produced
    # pipeline steps), rather than being dropped as pure GENERAL_CHAT (which
    # always returns steps=[]).
    assert len(result["steps"]) > 0
    assert result["execution_trace"]["routing_status"] == "RESOLVED"
    # The plan the agent actually consumed is recorded on the trace.
    assert result["execution_trace"]["runtime_metrics"]["plan_steps"] == 2
    # The session now reflects what was actually inspected (RAM), proving
    # the second step's evidence — not just the first step's explanation —
    # updated investigation state.
    assert agent._session_context.active_concept == "memory"


def test_agent_still_uses_single_shot_routing_for_non_explain_plans() -> None:
    """The EXTERNAL-then-GENERATE plan shape is intentionally *not*
    special-cased by the new integration: RoutingStatus.EXTERNAL_VERIFICATION
    already executes it correctly end-to-end (the full compound request is
    sent to the assessment model together with the verified facts, and the
    unavailable path already fails closed without fabricating a value —
    GA2-C07/F07). This guards against silently disabling that existing,
    working path when adding new plan-kind handling in the future.
    """
    from src.agent.runtime_factory import create_deterministic_agent

    agent = create_deterministic_agent()
    decision = agent._route_request(
        "Tìm phiên bản Python mới nhất rồi viết Dockerfile dùng phiên bản đó."
    )
    assert decision.status.name == "EXTERNAL_VERIFICATION"


# ---------------------------------------------------------------------------
# GA2-D08 — RAW / EXPLAIN_PREVIOUS runtime behavior (SHORT was already
# applied at runtime; RAW/EXPLAIN_PREVIOUS previously only persisted to
# session state via with_answer_shape() and were never consumed by response
# construction).
# ---------------------------------------------------------------------------


def _make_fact(metric: str, value: object, *, target: str = "monitor"):
    from datetime import datetime, timezone

    from src.pipeline.fact import Fact, FactFreshness, FactValidity
    from src.pipeline.provenance import Provenance

    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    provenance = Provenance("linux", "collector", target, now)
    return Fact(
        "system",
        metric,
        value,
        "percent",
        now,
        now,
        "linux",
        target,
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )


def _make_agent_with_mocks():
    from unittest import mock

    from src.agent.deterministic_agent import DeterministicAgent
    from src.model.assessment_model_adapter import AssessmentModelAdapter
    from src.pipeline.execution_engine import ExecutionEngine

    mock_engine = mock.MagicMock(spec=ExecutionEngine)
    mock_model = mock.MagicMock(spec=AssessmentModelAdapter)
    agent = DeterministicAgent(execution_engine=mock_engine, assessment_model=mock_model)
    return agent, mock_engine, mock_model


def test_raw_answer_shape_renders_compact_facts_instead_of_prose() -> None:
    from src.pipeline.fact_set import FactSet
    from src.pipeline.investigation_request import InvestigationRequest

    agent, _mock_engine, mock_model = _make_agent_with_mocks()
    investigation = InvestigationRequest(
        raw_request="chỉ số liệu",
        fact_set=FactSet((_make_fact("memory.usage", 42),)),
    )

    response = agent._assess("chỉ số liệu", investigation)

    assert "monitor.memory.usage = 42 percent" in response
    assert "source=linux" in response
    # RAW is a deterministic rendering; the LLM must never be consulted.
    mock_model.assess.assert_not_called()


def test_raw_answer_shape_falls_through_when_no_facts_collected() -> None:
    """RAW must not swallow a genuine refusal/error into an empty response
    when nothing was actually collected."""
    from src.pipeline.fact_set import FactSet
    from src.pipeline.investigation_request import InvestigationRequest

    agent, _mock_engine, mock_model = _make_agent_with_mocks()
    mock_model.assess.return_value = "Không thu thập được bằng chứng nào."
    investigation = InvestigationRequest(
        raw_request="chỉ số liệu",
        fact_set=FactSet(()),
    )

    response = agent._assess("chỉ số liệu", investigation)

    # Fell through to the normal (here: LLM) path rather than returning
    # an empty raw rendering.
    mock_model.assess.assert_called_once()
    assert response == "Không thu thập được bằng chứng nào."


class _FakeConversationStore:
    """Minimal in-memory ConversationStoreProtocol implementation for
    multi-turn GA2-D08/E02 tests (no filesystem, no summarization)."""

    def __init__(self) -> None:
        self._history: list[dict[str, object]] = []
        self._investigation_context = None

    @property
    def history(self) -> list[dict[str, object]]:
        return list(self._history)

    def add_turn(self, user: str, assistant: str) -> None:
        self._history.append({"role": "user", "content": user})
        self._history.append({"role": "assistant", "content": assistant})

    def set_summarize_fn(self, fn) -> None:
        pass

    def set_investigation_context(self, context: object) -> None:
        self._investigation_context = context

    @property
    def investigation_context(self):
        return self._investigation_context


def test_explain_previous_explains_last_answer_without_rerunning_collectors() -> None:
    """GA2-D08 acceptance scenario (turn 3 of the multi-turn example):
    'giải thích thêm' must explain the previous turn's answer and must not
    invoke the execution engine (no collector rerun) unless the user
    explicitly asks for a refresh.
    """
    agent, mock_engine, mock_model = _make_agent_with_mocks()
    store = _FakeConversationStore()
    agent.conversation_store = store
    mock_model.assess_raw.return_value = "RAM là bộ nhớ tạm thời của máy."

    # Seed turn 1+2 history: a previous resolved answer already exists.
    store.add_turn("kiểm tra RAM trên monitor", "monitor.memory.usage = 42 percent")

    result = agent.run_with_steps("giải thích thêm")

    assert result["response"] == "RAM là bộ nhớ tạm thời của máy."
    mock_engine.execute.assert_not_called()
    # The chat() prompt sent to the model must carry the previous answer's
    # content, not a freshly-invented environment request.
    sent_prompt = mock_model.assess_raw.call_args[0][0]
    assert "monitor.memory.usage = 42 percent" in sent_prompt
    # History reflects exactly one new turn, keyed by what the user actually
    # typed — not the internal explain-prompt text.
    assert store.history[-2] == {"role": "user", "content": "giải thích thêm"}
    assert store.history[-1] == {
        "role": "assistant",
        "content": "RAM là bộ nhớ tạm thời của máy.",
    }


def test_explain_previous_with_no_prior_turn_is_explicit_not_fabricated() -> None:
    agent, mock_engine, _mock_model = _make_agent_with_mocks()
    agent.conversation_store = _FakeConversationStore()

    result = agent.run_with_steps("giải thích thêm")

    assert "không có câu trả lời trước đó" in result["response"].casefold()
    mock_engine.execute.assert_not_called()


def test_explain_previous_reruns_collectors_only_on_explicit_refresh() -> None:
    """The 'do not rerun collectors unless the user explicitly asks for a
    refresh' carve-out: an explicit refresh phrase must fall through to the
    normal pipeline instead of being intercepted as EXPLAIN_PREVIOUS."""
    agent, _mock_engine, _mock_model = _make_agent_with_mocks()
    store = _FakeConversationStore()
    agent.conversation_store = store
    store.add_turn("kiểm tra RAM trên monitor", "monitor.memory.usage = 42 percent")
    # Establish EXPLAIN_PREVIOUS session state as if a prior turn requested it.
    from src.agent.session_investigation_context import SessionInvestigationContext

    agent._session_context = SessionInvestigationContext(
        requested_answer_shape="EXPLAIN_PREVIOUS"
    )

    assert agent._explain_previous_response("chạy lại kiểm tra") is None


# ---------------------------------------------------------------------------
# GA2-E02 — hard source constraint must survive a target-clarification round
# trip (previously: any CLARIFICATION_REQUIRED return path skipped session
# persistence entirely, so a bare clarification answer like "monitor." on
# the next turn lost the source restriction and any previously-known target
# hint, resolving with source_constraints back at ANY).
# ---------------------------------------------------------------------------


def test_hard_source_constraint_survives_target_clarification_round_trip() -> None:
    from src.pipeline.request_semantics import SourceConstraint
    from src.pipeline.target_resolver import AmbiguousTargetError

    agent, mock_engine, _mock_model = _make_agent_with_mocks()
    mock_engine.execute.side_effect = AmbiguousTargetError("", ("monitor", "server-1"))

    result = agent.run_with_steps("Chỉ dùng Grafana kiểm tra CPU.")

    assert result["execution_trace"]["routing_status"] == "CLARIFICATION_REQUIRED"
    # The hard source restriction from turn 1 is not lost even though the
    # turn ended in clarification rather than a resolved investigation.
    assert agent._session_context.active_sources == (SourceConstraint.GRAFANA,)
    assert agent._session_context.pending_clarification_field == "target"

    # Turn 2: the bare clarification answer "monitor." must be read as the
    # target *and* keep the Grafana-only restriction — not reset to ANY.
    decision = agent._route_request("monitor.")
    assert decision.request_frame.target_raw == "monitor"
    assert decision.request_frame.source_constraints == (SourceConstraint.GRAFANA,)


def test_explicit_source_change_after_clarification_is_never_overridden() -> None:
    """A user explicitly naming a *different* source on the clarification
    answer must win — pending-clarification inheritance must never override
    an explicit new constraint the current turn actually states."""
    from src.pipeline.request_semantics import SourceConstraint
    from src.pipeline.target_resolver import AmbiguousTargetError

    agent, mock_engine, _mock_model = _make_agent_with_mocks()
    mock_engine.execute.side_effect = AmbiguousTargetError("", ("monitor", "server-1"))
    agent.run_with_steps("Chỉ dùng Grafana kiểm tra CPU.")
    assert agent._session_context.active_sources == (SourceConstraint.GRAFANA,)

    decision = agent._route_request("Chỉ dùng Zabbix, target monitor.")
    assert decision.request_frame.source_constraints == (SourceConstraint.ZABBIX,)


def test_pending_clarification_answer_guard_ignores_long_new_requests() -> None:
    """A long, clearly-new request right after a clarification question
    must not be misread as the clarification answer."""
    from src.pipeline.target_resolver import AmbiguousTargetError

    agent, mock_engine, _mock_model = _make_agent_with_mocks()
    mock_engine.execute.side_effect = AmbiguousTargetError("", ("monitor", "server-1"))
    agent.run_with_steps("Chỉ dùng Grafana kiểm tra CPU.")

    decision = agent._route_request(
        "Thực ra tôi muốn kiểm tra disk usage trên toàn bộ hệ thống luôn."
    )
    # Not swallowed as a bare target answer (it is 10+ words).
    assert decision.request_frame.target_raw != (
        "Thực ra tôi muốn kiểm tra disk usage trên toàn bộ hệ thống luôn."
    )
