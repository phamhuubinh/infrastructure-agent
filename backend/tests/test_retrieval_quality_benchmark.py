from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orion.knowledge.local_embeddings import model_status


def test_frozen_retrieval_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    benchmark = importlib.import_module("retrieval_quality_benchmark")
    expected = json.loads((root / "benchmarks" / "retrieval_v2_baseline.json").read_text())
    result = benchmark.run_baseline()
    assert result["ranker"] == expected["ranker"]
    assert result["corpus_version"] == expected["corpus_version"]
    assert result["query_count"] == expected["query_count"]
    assert result["filename_top1_rate"] == expected["filename_top1_rate"]
    assert result["provenance_accuracy"] == expected["provenance_accuracy"]
    assert result["leakage_count"] == expected["leakage_count"]
    for key, value in expected["metrics"].items():
        assert result["metrics"][key] == pytest.approx(value)
    assert {case["key"]: case["first_relevant_rank"] for case in result["cases"]} == (
        expected["first_relevant_rank"]
    )
    # These are baseline failures, not future semantic acceptance results.
    assert result["cases"][1]["retrieved"] == []
    assert result["cases"][2]["first_relevant_rank"] is None
    assert result["cases"][3]["first_relevant_rank"] is None
    assert result["cases"][4]["retrieved"] == ["acronym_distractor"]


def test_experimental_semantic_benchmark_matches_frozen_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if model_status() != "installed":
        pytest.skip("Optional local E5 model has not been provisioned")
    root = Path(__file__).parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    benchmark = importlib.import_module("semantic_retrieval_benchmark")
    frozen = json.loads((root / "benchmarks" / "retrieval_v2_semantic_phase3a.json").read_text())
    measured = benchmark.run_experiment()
    for ranker in ("baseline", "dense", "fusion"):
        for field in (
            "metrics",
            "filename_top1_rate",
            "provenance_accuracy",
            "leakage_count",
        ):
            assert measured[ranker][field] == frozen[ranker][field]
        assert {case["key"]: case["first_relevant_rank"] for case in measured[ranker]["cases"]} == {
            case["key"]: case["first_relevant_rank"] for case in frozen[ranker]["cases"]
        }
    assert measured["performance"]["windows"] > 0


def test_semantic_benchmark_rss_is_optional_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    benchmark = importlib.import_module("semantic_retrieval_benchmark")
    monkeypatch.setattr(benchmark.sys, "platform", "win32")
    assert benchmark._peak_rss_kb() is None
