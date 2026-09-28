from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


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
