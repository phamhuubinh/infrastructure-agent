from __future__ import annotations

from unittest import mock

from src.agent.conversation_store import ConversationStore
from src.agent.deterministic_agent import DeterministicAgent
from src.agent.session_investigation_context import (
    SessionContextResolver,
    SessionInvestigationContext,
)
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.normalizer import Normalizer
from src.pipeline.request_semantics import SourceConstraint


class _CapturingEngine:
    def __init__(self) -> None:
        self.frames = []

    def execute(self, frame):
        resolved = frame.evolve(target_resolved=frame.target_raw or "localhost")
        self.frames.append(resolved)
        return InvestigationRequest(
            raw_request=resolved.raw_request,
            request_frame=resolved,
            semantic_request=resolved,
            extracted_params=resolved.parameters,
            answer_type=resolved.answer_type,
        )


def test_follow_up_inherits_target_before_execution(tmp_path) -> None:
    store = ConversationStore("context-agent", store_dir=str(tmp_path))
    engine = _CapturingEngine()
    model = mock.Mock()
    model.assess_raw.return_value = "summary"
    agent = DeterministicAgent(engine, model, conversation_store=store)

    agent.execute_pipeline_only("Kiểm tra CPU trên monitor")
    follow_up = agent.execute_pipeline_only("Còn RAM?")

    assert follow_up.request_frame is not None
    assert follow_up.request_frame.target_resolved == "monitor"
    assert follow_up.request_frame.context_applied == ("target",)


def test_explicit_target_overrides_active_context() -> None:
    context = SessionInvestigationContext(active_target="monitor")
    frame = Normalizer().normalize("Kiểm tra disk trên server02")

    resolved = SessionContextResolver().resolve(frame, context)

    assert resolved.target_raw == "server02"
    assert "target" not in resolved.context_applied


def test_switch_target_clears_target_scoped_resources() -> None:
    context = SessionInvestigationContext(
        active_target="monitor",
        active_concept="service",
        active_service="nginx",
        active_path="/var/log/nginx",
        active_sources=(SourceConstraint.GRAFANA,),
        active_excluded_sources=(SourceConstraint.INTERNET,),
    )

    switched = context.switch_target("server02")

    assert switched.active_target == "server02"
    assert switched.active_service is None
    assert switched.active_path is None
    assert switched.active_concept is None
    assert switched.active_sources == ()
    assert switched.active_excluded_sources == ()


def test_explicit_source_replaces_prior_source_and_clears_stale_exclusion() -> None:
    context = SessionInvestigationContext(
        active_target="monitor",
        active_sources=(SourceConstraint.GRAFANA,),
        active_excluded_sources=(SourceConstraint.INTERNET,),
    )
    frame = Normalizer().normalize("Chỉ dùng Zabbix kiểm tra CPU trên monitor")

    updated = context.update_from_frame(frame.evolve(target_resolved="monitor"))

    assert updated.active_sources == (SourceConstraint.ZABBIX,)
    assert updated.active_excluded_sources == ()


def test_unresolved_new_target_does_not_replace_validated_context() -> None:
    context = SessionInvestigationContext(active_target="monitor")
    unresolved = Normalizer().normalize("Kiểm tra CPU trên doesnotexist123")

    updated = context.update_from_frame(unresolved)

    assert updated.active_target == "monitor"


def test_context_persists_without_raw_evidence(tmp_path) -> None:
    store = ConversationStore("context-persist", store_dir=str(tmp_path))
    context = SessionInvestigationContext(
        active_target="monitor",
        active_concept="memory",
        incident_ids=("INC-407",),
    )
    store.set_investigation_context(context)

    reloaded = ConversationStore("context-persist", store_dir=str(tmp_path))

    assert reloaded.investigation_context == context
    assert reloaded.history == []


def test_reset_request_clears_context_without_model_or_execution(tmp_path) -> None:
    store = ConversationStore("context-reset", store_dir=str(tmp_path))
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor", active_concept="cpu")
    )
    engine = _CapturingEngine()
    model = mock.Mock()
    agent = DeterministicAgent(engine, model, conversation_store=store)

    response = agent.run("reset context")

    assert response == "Đã xóa ngữ cảnh điều tra đang hoạt động."
    assert store.investigation_context == SessionInvestigationContext()
    assert engine.frames == []
    model.assess.assert_not_called()
    model.assess_raw.assert_not_called()


def test_ambiguous_service_pronoun_requests_the_missing_service(tmp_path) -> None:
    store = ConversationStore("context-pronoun", store_dir=str(tmp_path))
    store.set_investigation_context(
        SessionInvestigationContext(active_target="monitor")
    )
    engine = _CapturingEngine()
    model = mock.Mock()
    agent = DeterministicAgent(engine, model, conversation_store=store)

    result = agent.run_with_steps("service đó bị lỗi")

    assert result["execution_trace"]["answer_strategy"] == "CLARIFICATION"
    assert "service nào" in result["response"]
    assert engine.frames == []


def test_concurrent_sessions_do_not_bleed_targets(tmp_path) -> None:
    monitor_store = ConversationStore("context-monitor", store_dir=str(tmp_path))
    database_store = ConversationStore("context-database", store_dir=str(tmp_path))
    monitor_engine = _CapturingEngine()
    database_engine = _CapturingEngine()
    monitor_agent = DeterministicAgent(
        monitor_engine, mock.Mock(), conversation_store=monitor_store
    )
    database_agent = DeterministicAgent(
        database_engine, mock.Mock(), conversation_store=database_store
    )

    monitor_agent.execute_pipeline_only("Kiểm tra CPU trên monitor")
    database_agent.execute_pipeline_only("Kiểm tra CPU trên database")
    monitor_agent.execute_pipeline_only("Còn RAM?")
    database_agent.execute_pipeline_only("Còn RAM?")

    assert monitor_engine.frames[-1].target_resolved == "monitor"
    assert database_engine.frames[-1].target_resolved == "database"


def test_follow_up_preserves_hard_source_constraint(tmp_path) -> None:
    store = ConversationStore("context-source", store_dir=str(tmp_path))
    engine = _CapturingEngine()
    agent = DeterministicAgent(engine, mock.Mock(), conversation_store=store)

    agent.execute_pipeline_only("Chỉ dùng Grafana để lấy CPU của monitor")
    follow_up = agent.execute_pipeline_only("Còn RAM thì sao?")

    assert follow_up.request_frame is not None
    assert follow_up.request_frame.source_constraints == (SourceConstraint.GRAFANA,)
    assert "source" in follow_up.request_frame.context_applied
