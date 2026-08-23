from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.canonical_factory import (
    CanonicalProductionRuntime,
    create_canonical_production_runtime,
    create_canonical_session_agent,
)
from src.agent.contracts import (
    AgentDecision,
    DecisionKind,
)
from src.agent.permissions import (
    PermissionMode,
)
from src.agent.runtime import (
    RuntimeTerminal,
)
from src.model.agent_provider_bridge import (
    AssessmentAgentProvider,
)
from src.model.assessment_model_adapter import (
    AssessmentModelAdapter,
)
from src.model.providers.fallback_adapter import (
    FallbackAssessmentAdapter,
)
from src.shared.config import OrionConfig
from src.model.unconfigured_adapter import (
    UnconfiguredAssessmentAdapter,
)


class FinalAssessmentAdapter(
    AssessmentModelAdapter
):
    def assess(
        self,
        assessment_request,
    ) -> str:
        return self.assess_raw("")

    def assess_raw(
        self,
        prompt: str,
    ) -> str:
        decision = AgentDecision(
            kind=DecisionKind.FINAL,
            goal="answer request",
            answer="factory-ok",
        )
        return json.dumps(
            decision.to_wire()
        )


def _empty_config() -> OrionConfig:
    return OrionConfig(
        servers={},
        active_server_name="",
        tools={},
    )


def test_factory_builds_canonical_runtime_with_injected_model(
    tmp_path: Path,
) -> None:
    bundle = (
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            assessment_adapter=(
                FinalAssessmentAdapter()
            ),
            config=_empty_config(),
        )
    )

    assert isinstance(
        bundle,
        CanonicalProductionRuntime,
    )

    result = bundle.runtime.run(
        "hello",
        permission_mode=(
            PermissionMode.READ
        ),
    )

    assert (
        result.terminal
        is RuntimeTerminal.FINAL
    )
    assert (
        result.response_text
        == "factory-ok"
    )


def test_factory_provider_is_canonical_bridge(
    tmp_path: Path,
) -> None:
    bundle = (
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            assessment_adapter=(
                FinalAssessmentAdapter()
            ),
            config=_empty_config(),
        )
    )

    assert len(bundle.providers) == 1
    assert isinstance(
        bundle.providers[0],
        AssessmentAgentProvider,
    )


def test_factory_preserves_configured_fallback_order(
    tmp_path: Path,
) -> None:
    config = OrionConfig(
        servers={
            "primary": {
                "base_url": (
                    "http://primary:8000"
                ),
                "model": "model-a",
            },
            "backup": {
                "base_url": (
                    "http://backup:8000"
                ),
                "model": "model-b",
            },
        },
        active_server_name="primary",
        fallback_chain=["backup"],
        tools={},
    )

    bundle = (
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            config=config,
        )
    )

    assert (
        len(bundle.assessment_adapters)
        == 2
    )
    assert len(bundle.providers) == 2
    assert isinstance(
        bundle.assessment_model,
        FallbackAssessmentAdapter,
    )


def test_factory_supports_setup_mode_without_model_configuration(
    tmp_path: Path,
) -> None:
    bundle = (
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            config=_empty_config(),
        )
    )

    assert isinstance(
        bundle.assessment_model,
        UnconfiguredAssessmentAdapter,
    )
    assert bundle.providers == ()


def test_factory_registry_and_knowledge_tool_share_registrations(
    tmp_path: Path,
) -> None:
    bundle = (
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            assessment_adapter=(
                FinalAssessmentAdapter()
            ),
            config=_empty_config(),
        )
    )

    assert tuple(
        sorted(
            bundle.target_registry
            .target_names()
        )
    ) == tuple(
        sorted(
            bundle.knowledge_tool
            .source_names()
        )
    )



class _SessionStore:
    def __init__(self) -> None:
        self.turns = []
        self.summarize_fn = None

    @property
    def history(self):
        return []

    def add_turn(self, user, assistant):
        self.turns.append((user, assistant))

    def set_summarize_fn(self, fn):
        self.summarize_fn = fn


def test_factory_builds_session_agent_over_exact_runtime(
    tmp_path: Path,
) -> None:
    store = _SessionStore()

    agent = create_canonical_session_agent(
        target_store_path=str(
            tmp_path / "targets.json"
        ),
        assessment_adapter=(
            FinalAssessmentAdapter()
        ),
        conversation_store=store,
        config=_empty_config(),
    )

    payload = agent.run_with_steps(
        "hello"
    )

    assert payload["response"] == (
        "factory-ok"
    )
    assert store.turns == [
        ("hello", "factory-ok")
    ]
    assert callable(store.summarize_fn)


def test_session_factory_preserves_setup_mode_without_execution(
    tmp_path: Path,
) -> None:
    store = _SessionStore()

    agent = create_canonical_session_agent(
        target_store_path=str(
            tmp_path / "targets.json"
        ),
        conversation_store=store,
        config=_empty_config(),
    )

    payload = agent.run_with_steps(
        "hello"
    )

    assert agent.health_check() is False
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
