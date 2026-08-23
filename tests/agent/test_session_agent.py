from __future__ import annotations

import json

from src.agent.authority import (
    AuthorityBudget,
)
from src.agent.contracts import (
    AgentObservation,
    ObservationStatus,
)
from src.agent.permissions import (
    PermissionMode,
)
from src.agent.runtime import (
    AgentRuntimeResult,
    RuntimeFailureReason,
    RuntimeTerminal,
)
from src.agent.session_agent import (
    CanonicalSessionAgent,
)
from src.model.assessment_model_adapter import (
    AssessmentModelAdapter,
)


class FakeAssessmentModel(
    AssessmentModelAdapter
):
    def __init__(self) -> None:
        self.summarize_calls = 0

    def assess(self, request) -> str:
        return "unused"

    def assess_raw(
        self,
        prompt: str,
    ) -> str:
        self.summarize_calls += 1
        return "summary"

    def health_check(
        self,
        timeout: float = 5.0,
    ) -> bool:
        return True


class FakeStore:
    def __init__(self) -> None:
        self._history = [
            {
                "role": "user",
                "content": (
                    "Earlier question about monitor"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Earlier answer."
                ),
            },
        ]
        self.turns: list[
            tuple[str, str]
        ] = []
        self.summarize_fn = None

    @property
    def history(self):
        return list(self._history)

    def add_turn(
        self,
        user: str,
        assistant: str,
    ) -> None:
        self.turns.append(
            (user, assistant)
        )
        self._history.extend(
            [
                {
                    "role": "user",
                    "content": user,
                },
                {
                    "role": "assistant",
                    "content": assistant,
                },
            ]
        )

    def set_summarize_fn(
        self,
        fn,
    ) -> None:
        self.summarize_fn = fn


class FakeRuntime:
    def __init__(
        self,
        result: AgentRuntimeResult,
    ) -> None:
        self.result = result
        self.requests: list[
            dict[str, object]
        ] = []

    def run(
        self,
        request: str,
        *,
        permission_mode,
        budget=None,
        approval=None,
        request_id=None,
    ) -> AgentRuntimeResult:
        self.requests.append(
            {
                "request": request,
                "permission_mode": (
                    permission_mode
                ),
                "request_id": request_id,
            }
        )
        return self.result


def _result(
    *,
    response: str = "Canonical answer.",
    observations=(),
    terminal=RuntimeTerminal.FINAL,
    failure=None,
) -> AgentRuntimeResult:
    return AgentRuntimeResult(
        terminal=terminal,
        response_text=response,
        observations=tuple(
            observations
        ),
        budget=AuthorityBudget(),
        model_calls=1,
        discovery_calls=0,
        action_attempts=0,
        failure=failure,
    )


def test_session_agent_passes_bounded_history_as_context() -> None:
    runtime = FakeRuntime(
        _result()
    )
    store = FakeStore()

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            FakeAssessmentModel()
        ),
        conversation_store=store,
    )

    payload = agent.run_with_steps(
        "What about memory?"
    )

    assert payload["response"] == (
        "Canonical answer."
    )

    envelope = json.loads(
        runtime.requests[0]["request"]
    )

    assert envelope[
        "current_request"
    ] == "What about memory?"

    assert envelope[
        "conversation_context"
    ][0]["content"] == (
        "Earlier question about monitor"
    )

    assert (
        envelope["context_policy"]
        .startswith(
            "Conversation and attachment"
        )
    )

    assert store.turns == [
        (
            "What about memory?",
            "Canonical answer.",
        )
    ]


def test_attachment_context_never_grants_authority_or_leaks_secrets() -> None:
    runtime = FakeRuntime(
        _result()
    )

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            FakeAssessmentModel()
        ),
    )

    agent.run_with_steps(
        "Summarize attachment.",
        attachment_evidence=(
            {
                "text": (
                    "status ok "
                    "token=attachment-secret"
                ),
                "api_key": (
                    "never-expose"
                ),
                "target": "monitor",
            },
        ),
    )

    request = runtime.requests[0][
        "request"
    ]

    assert isinstance(
        request,
        str,
    )

    assert (
        "attachment-secret"
        not in request
    )
    assert "never-expose" not in request

    envelope = json.loads(request)

    assert (
        "capability"
        in envelope["context_policy"]
    )
    assert (
        envelope[
            "attachment_context"
        ][0]["target"]
        == "monitor"
    )


def test_steps_expose_metadata_not_raw_fact_values() -> None:
    observation = AgentObservation(
        action_id=1,
        capability_id="host.get_cpu",
        status=ObservationStatus.SUCCESS,
        facts=(
            {
                "logical_cores": 4,
                "token": "raw-secret",
            },
        ),
        target_ref="monitor",
        provenance={
            "source": "monitor",
            "resource": "get_cpu",
        },
    )

    runtime = FakeRuntime(
        _result(
            observations=(
                observation,
            )
        )
    )

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            FakeAssessmentModel()
        ),
    )

    payload = agent.run_with_steps(
        "Inspect monitor."
    )

    step = payload["steps"][0]

    assert step["type"] == "evidence"
    assert (
        step["capability_id"]
        == "host.get_cpu"
    )
    assert step["target_id"] == (
        "monitor"
    )

    rendered = json.dumps(payload)

    assert "logical_cores" not in rendered
    assert "raw-secret" not in rendered


def test_public_trace_never_echoes_runtime_request() -> None:
    runtime = FakeRuntime(
        _result()
    )

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            FakeAssessmentModel()
        ),
    )

    payload = agent.run_with_steps(
        "check token=top-secret"
    )

    trace = payload[
        "execution_trace"
    ]

    assert trace["user_request"] == ""
    assert (
        trace["runtime_metrics"]
        ["canonical_runtime"]
        ["terminal"]
        == "final"
    )

    rendered = json.dumps(trace)

    assert "top-secret" not in rendered
    assert "system_prompt" not in rendered
    assert "user_prompt" not in rendered


def test_failed_runtime_has_safe_trace() -> None:
    runtime = FakeRuntime(
        _result(
            response=(
                "Unable to complete request."
            ),
            terminal=(
                RuntimeTerminal.FAILED
            ),
            failure=(
                RuntimeFailureReason
                .MODEL_FAILURE
            ),
        )
    )

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            FakeAssessmentModel()
        ),
    )

    payload = agent.run_with_steps(
        "hello"
    )

    canonical = (
        payload["execution_trace"]
        ["runtime_metrics"]
        ["canonical_runtime"]
    )

    assert canonical["terminal"] == (
        "failed"
    )
    assert canonical["failure"] == (
        "model_failure"
    )


def test_store_receives_model_summarizer() -> None:
    model = FakeAssessmentModel()
    store = FakeStore()

    CanonicalSessionAgent(
        runtime=FakeRuntime(
            _result()
        ),
        assessment_model=model,
        conversation_store=store,
    )

    assert callable(
        store.summarize_fn
    )
    assert (
        store.summarize_fn("history")
        == "summary"
    )


def test_health_check_delegates_to_model() -> None:
    agent = CanonicalSessionAgent(
        runtime=FakeRuntime(
            _result()
        ),
        assessment_model=(
            FakeAssessmentModel()
        ),
    )

    assert agent.health_check() is True


def test_setup_mode_never_calls_runtime() -> None:
    from src.model.unconfigured_adapter import (
        UnconfiguredAssessmentAdapter,
    )

    runtime = FakeRuntime(
        _result()
    )

    store = FakeStore()

    agent = CanonicalSessionAgent(
        runtime=runtime,
        assessment_model=(
            UnconfiguredAssessmentAdapter()
        ),
        conversation_store=store,
    )

    payload = agent.run_with_steps(
        "hello"
    )

    assert runtime.requests == []
    assert "No model is configured" in (
        payload["response"]
    )

    canonical = (
        payload["execution_trace"]
        ["runtime_metrics"]
        ["canonical_runtime"]
    )

    assert canonical["terminal"] == (
        "setup_required"
    )
    assert canonical["model_calls"] == 0
    assert canonical[
        "action_attempts"
    ] == 0
