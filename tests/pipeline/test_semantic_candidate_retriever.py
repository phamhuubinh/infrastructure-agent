from __future__ import annotations

from src.pipeline.semantic_candidate_retriever import (
    SemanticCandidate,
    SemanticCandidateRetriever,
)


def _retriever() -> SemanticCandidateRetriever:
    return SemanticCandidateRetriever(
        {
            "cpu": ("cpu", "processor"),
            "memory": ("memory", "ram"),
            "service": ("service", "dịch vụ"),
        }
    )


def test_retrieval_returns_candidates_without_selecting_route() -> None:
    candidates = _retriever().retrieve("sevice nao bi loi")

    assert candidates[0].label == "service"
    assert candidates[0].source == "lexical_fuzzy"


def test_exact_match_requires_token_or_phrase_boundaries() -> None:
    retriever = SemanticCandidateRetriever({"disk": ("ổ",)})

    candidate = retriever.retrieve("foo bar")[0]

    assert candidate.source == "lexical_fuzzy"
    assert candidate.score < 0.72


def test_validation_requires_threshold_and_margin() -> None:
    candidates = (
        SemanticCandidate("server01", 0.83, "server01", "lexical_fuzzy"),
        SemanticCandidate("server02", 0.81, "server02", "lexical_fuzzy"),
    )

    validation = SemanticCandidateRetriever.validate(
        candidates,
        threshold=0.78,
        margin_threshold=0.08,
    )

    assert not validation.accepted
    assert validation.reason == "ambiguous_margin"
    assert validation.margin is not None and validation.margin < 0.08


def test_validation_rejects_operation_incompatible_candidate() -> None:
    candidates = (SemanticCandidate("configure", 0.95, "config", "exact"),)

    validation = SemanticCandidateRetriever.validate(
        candidates,
        threshold=0.7,
        margin_threshold=0.05,
        compatible=lambda label: label != "configure",
    )

    assert not validation.accepted
    assert validation.reason == "no_compatible_candidate"
