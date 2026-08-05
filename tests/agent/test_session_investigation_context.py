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
    )

    switched = context.switch_target("server02")

    assert switched.active_target == "server02"
    assert switched.active_service is None
    assert switched.active_path is None
    assert switched.active_concept is None


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
