from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.canonical_factory import (
    CanonicalProductionRuntime,
    create_canonical_production_runtime,
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
from src.shared.config_errors import (
    InvalidConfigValueError,
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


def test_factory_rejects_missing_model_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        InvalidConfigValueError
    ):
        create_canonical_production_runtime(
            target_store_path=str(
                tmp_path / "targets.json"
            ),
            config=_empty_config(),
        )


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
