"""Offline Phase 3C selector and real-ingestion benchmark acceptance."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from orion.contracts import DocumentRef, KnowledgeSourceRef, RetrievedSegment
from orion.knowledge.evidence_selection import select_document_balanced
from orion.knowledge.local_embeddings import model_status


def _hit(document_id: str, segment_id: str, score: float) -> RetrievedSegment:
    return RetrievedSegment(
        document=DocumentRef(
            document_id=document_id,
            source=KnowledgeSourceRef(kind="project", source_id="project-a"),
            name=f"{document_id}.md",
            media_type="text/markdown",
        ),
        segment_id=segment_id,
        text=f"original text {segment_id}",
        page=2,
        section="Original section",
        score=score,
    )


def test_first_pass_then_original_order_fill_and_identity() -> None:
    hits = (
        _hit("a", "a1", 9.0),
        _hit("a", "a2", 8.0),
        _hit("b", "b1", 7.0),
        _hit("c", "c1", 6.0),
        _hit("b", "b2", 5.0),
        _hit("a", "a3", 4.0),
    )
    selected = select_document_balanced(hits, 5)
    assert [hit.segment_id for hit in selected] == ["a1", "b1", "c1", "a2", "b2"]
    assert selected == select_document_balanced(hits, 5)
    assert all(any(hit is original for original in hits) for hit in selected)
    assert selected[0].score == 9.0
    assert selected[0].text == "original text a1"
    assert selected[0].page == 2 and selected[0].section == "Original section"
    assert selected[0].document.source.source_id == "project-a"
    assert select_document_balanced(hits, 1) == (hits[0],)
    assert select_document_balanced(hits, 20) == (
        hits[0],
        hits[2],
        hits[3],
        hits[1],
        hits[4],
        hits[5],
    )


def test_single_document_duplicate_segments_and_bounded_input() -> None:
    hits = tuple(_hit("only", f"s{index}", float(100 - index)) for index in range(52))
    assert [hit.segment_id for hit in select_document_balanced(hits, 3)] == ["s0", "s1", "s2"]
    assert len(select_document_balanced(hits, 100)) == 50
    with_duplicate = (hits[0], hits[0], hits[1], hits[1], hits[2])
    assert [hit.segment_id for hit in select_document_balanced(with_duplicate, 5)] == [
        "s0",
        "s1",
        "s2",
    ]
    assert select_document_balanced(hits, 0) == ()


def _benchmark(monkeypatch: pytest.MonkeyPatch):
    root = Path(__file__).parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    return importlib.import_module("document_balance_benchmark")


def test_phase3c_real_ingestion_measurement_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).parents[1]
    benchmark = _benchmark(monkeypatch)
    expected = json.loads(
        (root / "benchmarks" / "retrieval_v2_document_balance_phase3c.json").read_text()
    )
    first = benchmark.run_experiment()
    assert first == expected == benchmark.run_experiment()
    assert first["document_segment_counts"]["saturn_dominant"] >= 4
    assert first["document_segment_counts"]["cobalt_single"] >= 3
    measured = first["modes"]["baseline"]
    cases = {case["key"]: case for case in measured["cases"]}
    dominant = cases["dominant_repetition"]
    assert dominant["raw"]["relevant_documents_represented@k"] == 1
    assert dominant["selected"]["relevant_documents_represented@k"] == 2
    assert set(dominant["selected"]["documents"]) <= set(dominant["candidate_documents"])
    single = cases["single_document_fill"]
    assert single["raw"]["result_count"] == single["selected"]["result_count"] == 3
    assert single["selected"]["documents"] == ["cobalt_single"] * 3
    three = cases["three_relevant_documents"]
    first_seen = list(dict.fromkeys(three["candidate_documents"]))[:3]
    assert three["selected"]["documents"] == first_seen
    assert cases["exact_filename"]["selected"]["documents"][0] == "saturn_dominant"
    assert cases["project_session_scope"]["selected"]["leakage_count"] == 0
    assert cases["deleted_exclusion"]["selected"]["leakage_count"] == 0
    summary = measured["summary"]
    assert (
        summary["selected"]["multi_document_coverage@k"]
        > summary["raw"]["multi_document_coverage@k"]
    )
    for metric in ("recall@1", "recall@k", "mrr@k", "ndcg@k"):
        assert summary["selected"][metric] >= summary["raw"][metric]
    assert summary["selected"]["exact_filename_top_one"] is True
    assert summary["selected"]["provenance_accuracy"] == 1.0
    assert summary["selected"]["leakage_count"] == 0


def test_frozen_phase3a_artifacts_are_byte_for_byte_unchanged() -> None:
    root = Path(__file__).parents[1] / "benchmarks"
    expected = {
        "retrieval_v2_corpus.json": (
            "43b82b6704b7077254d7ce5e9b696d9873c801b0cbeab3f29b0b209fbc851ff0"
        ),
        "retrieval_v2_baseline.json": (
            "ad392fa2062086fb27bb277884af3c2b966348f2f087fe85a2824f3b762d39ab"
        ),
        "retrieval_v2_semantic_phase3a.json": (
            "61919519b9ffd52c2a350f3adeaec6178cf3fd4cc3fa33287da4c22675b17fbf"
        ),
    }
    for name, digest in expected.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest


def test_optional_e5_phase3c_measurement_matches_recorded_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if model_status() != "installed":
        pytest.skip("Optional local E5 model has not been provisioned")
    root = Path(__file__).parents[1]
    benchmark = _benchmark(monkeypatch)
    expected = json.loads(
        (root / "benchmarks" / "retrieval_v2_document_balance_phase3c_hybrid.json").read_text()
    )
    measured = benchmark.run_experiment(include_hybrid=True)
    assert measured["corpus_version"] == expected["corpus_version"]
    assert measured["candidate_depth"] == expected["candidate_depth"]
    hybrid = measured["modes"]["hybrid"]
    frozen = expected["modes"]["hybrid"]
    for mode in ("raw", "selected"):
        summary = hybrid["summary"][mode]
        frozen_summary = frozen["summary"][mode]
        for field in (
            "recall@1",
            "recall@k",
            "mrr@k",
            "ndcg@k",
            "multi_document_coverage@k",
            "provenance_accuracy",
        ):
            assert summary[field] == pytest.approx(frozen_summary[field])
        for field in (
            "multi_document_represented_count@k",
            "exact_filename_top_one",
            "leakage_count",
        ):
            assert summary[field] == frozen_summary[field]

    cases = {case["key"]: case for case in hybrid["cases"]}
    frozen_cases = {case["key"]: case for case in frozen["cases"]}
    assert cases.keys() == frozen_cases.keys()
    for key, case in cases.items():
        for mode in ("raw", "selected"):
            observed = case[mode]
            recorded = frozen_cases[key][mode]
            for field in (
                "first_relevant_rank",
                "relevant_documents_represented@k",
                "result_count",
                "exact_filename_top_one",
                "leakage_count",
            ):
                assert observed[field] == recorded[field]
            assert observed["provenance_accuracy"] == pytest.approx(recorded["provenance_accuracy"])
