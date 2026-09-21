from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orion.contracts import AssistantMessage, ModelTurn, ModelTurnCompleted
from orion.models.backend import ModelSettings


@pytest.mark.anyio
@pytest.mark.parametrize("case_ids", [None, (5, 6, 12, 15, 20, 13, 21, 24)])
async def test_semantic_harness_isolated_sessions_history_and_labeled_fault(
    monkeypatch, tmp_path, case_ids
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("targeted_semantic_qa")
    real_build = module.build_application
    blocked = []

    def build(**kwargs):  # type: ignore[no-untyped-def]
        blocked.append(kwargs["blocked_tool_operation_kinds"])
        app = real_build(**kwargs)
        app.runtime._infrastructure_targets = (("linux", "fixture-target", "Fixture"),)
        return app

    class Provider:
        diagnostics = []

        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            assert settings.model_id == "persisted-fixture"
            yield ModelTurnCompleted(
                turn=ModelTurn(assistant=AssistantMessage(content="Fixture response."))
            )

    monkeypatch.setattr(module, "build_application", build)
    monkeypatch.setattr(module, "DiagnosticProvider", Provider)
    monkeypatch.setattr(
        module,
        "active_model_settings",
        lambda: ModelSettings(
            provider_type="openai_compatible",
            base_url="http://fixture.invalid/v1",
            model_id="persisted-fixture",
            api_key="do-not-log-this-secret",
        ),
    )
    result = await module.run(tmp_path, case_ids=case_ids)
    rows = result["cases"]
    expected = list(range(1, 25)) if case_ids is None else [5, 6, 12, 13, 15, 19, 20, 21, 24]
    assert [row["case_id"] for row in rows] == expected
    assert result["executed_case_ids"] == expected
    assert result["requested_case_ids"] == (expected if case_ids is None else sorted(case_ids))
    assert len({row["session_id"] for row in rows}) == len(expected) - 2
    by_id = {row["case_id"]: row for row in rows}
    assert len({by_id[case_id]["session_id"] for case_id in (19, 20, 21)}) == 1
    assert by_id[19]["replay_role"] == ("requested" if case_ids is None else "prerequisite")
    assert all(row["prompt"] == module.cases("fixture-target")[row["case_id"] - 1] for row in rows)
    assert all(row["verdict"] == "INCONCLUSIVE" for row in rows)
    assert blocked == [frozenset({"mutation"})]
    assert all(not row["previous_tool_result_reused_in_context"] for row in rows)
    assert "999 CPU" in by_id[20]["injected_history"]
    assert any(
        "999 CPU" in text
        for check in by_id[20]["model_input_checks"]
        for text in check["assistant_history"]
    )
    if case_ids is None:
        assert by_id[23]["fault_injection"] is True
        assert by_id[23]["model_attempt_count"] == 2
        assert by_id[23]["tool_calls"][0]["error"]["code"] == "not_found"
    else:
        assert all(not row["fault_injection"] for row in rows)
    assert by_id[24]["terminal_citation_source_ref_ids"] == []
    serialized = (tmp_path / "metrics.json").read_text()
    assert "do-not-log-this-secret" not in serialized
    assert json.loads(serialized)["semantic_review_complete"] is False
    assert (tmp_path / "cases.csv").is_file()

    # Offline review includes prerequisite telemetry but keeps requested score separate.
    review_path = tmp_path / "adjudication.json"
    review_path.write_text(
        json.dumps(
            {
                "recommendation": "INCONCLUSIVE",
                "cases": {
                    str(case_id): {"verdict": "INCONCLUSIVE", "issue_tags": []}
                    for case_id in expected
                },
            }
        )
    )
    module.apply_reviews(tmp_path, review_path)
    reviewed = json.loads((tmp_path / "metrics.json").read_text())
    assert reviewed["requested_case_summary"]["verdict_counts"] == {
        "INCONCLUSIVE": 24 if case_ids is None else 8
    }
    assert reviewed["summary"]["verdict_counts"] == {"INCONCLUSIVE": len(expected)}


def test_semantic_harness_redacts_explicit_secrets_and_does_not_score_completion(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("targeted_semantic_qa")
    assert module.sanitize(
        {"api_key": "hidden", "text": "value secret-value"}, ("secret-value",)
    ) == {
        "api_key": "[REDACTED]",
        "text": "value [REDACTED]",
    }
    assert len(module.cases("resolved-target")) == 24


@pytest.mark.parametrize(
    "selected,expected", [((20,), [19, 20]), ((21,), [19, 20, 21]), ((16,), [16])]
)
def test_selected_case_prerequisites(monkeypatch, selected, expected):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("targeted_semantic_qa")
    assert module.select_cases(selected) == (list(selected), expected)


@pytest.mark.parametrize("selected", [(), (0,), (25,), ("20",)])
def test_invalid_selection_rejected_before_live_calls(monkeypatch, selected):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module("targeted_semantic_qa")
    with pytest.raises(ValueError):
        module.select_cases(selected)
