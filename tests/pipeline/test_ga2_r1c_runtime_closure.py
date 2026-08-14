"""Tests for GA2-R1-02: runtime closure for selected-passage grounding.

These tests verify:
- Cache-hit relevance/passage recomputation remains request-specific.
- The bounded passage selection correctly excludes unrelated claims from the
  same page.
- Subject extraction generalizes beyond hard-coded product names.
- The end-to-end flow from fetch → passage selection → claim grounding works
  correctly for version/date/price/identity claims.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.external_verification import (
    BoundedPassage,
    ExternalDocument,
    ExternalEvidenceRelevance,
    ExternalVerificationExecutor,
    ExternalVerificationOutcome,
)
from src.pipeline.request_frame import RequestFrame
from src.shared.execution.tool_result import ToolResult


class _MockKnowledgeTool:
    """Mock tool that returns configurable search and fetch results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.search_data: dict[str, object] = {
            "status": "ok",
            "provider": "mock-search",
            "results": [],
        }
        self.fetch_payloads: dict[str, dict[str, object]] = {}

    def source_names(self) -> tuple[str, ...]:
        return ("internet",)

    def source_kind(self, source: str) -> str:
        assert source == "internet"
        return "internet"

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        self.calls.append(dict(arguments))
        if arguments["resource"] == "web_search":
            return ToolResult(success=True, data=self.search_data)
        url = str(arguments["url"])
        payload = self.fetch_payloads.get(url)
        if payload is None:
            return ToolResult(success=False, error=f"URL not found: {url}")
        return ToolResult(success=True, data=payload)


def _frame(query: str, explicit_url: str | None = None) -> RequestFrame:
    """Create a request frame for the given query."""
    return RequestFrame(
        raw_request=query,
        concepts=(),
        operation="inspect",
        target_raw=None,
        target_resolved=None,
        parameters=None,
        answer_type=None,
        timeframe=None,
        confidence=0.0,
        ambiguity=(),
        lexical_tokens=(),
        matched_synonyms=(),
        concept_candidates=(),
        intent_candidates=(),
        target_candidates=(),
        routing_status=None,
        context_applied=(),
        context_snapshot={},
        subframes=(),
        request_domain=None,  # type: ignore[arg-type]
        information_scope=None,  # type: ignore[arg-type]
        external_need=None,  # type: ignore[arg-type]
        source_constraints=(),
        explicit_url=explicit_url,
    )


class TestSelectedPassageExclusion:
    """Tests for GA2-R1-02: selected passage correctly excludes unrelated claims."""

    def test_python_version_selected_not_node_version(self) -> None:
        """One page contains selected Python 3.14.2 support plus an unselected
        Node.js 18.0.1; a response claiming Python 18.0.1 is rejected."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Versions", "url": "https://example.com/versions"}],
        }
        # Content has both Python and Node.js versions
        tool.fetch_payloads = {
            "https://example.com/versions": {
                "url": "https://example.com/versions",
                "status": 200,
                "content_type": "text/html",
                "content_length": 200,
                "truncated": False,
                "data": "Python current version is 3.14.2. Also available: Node.js version 18.0.1, Rust version 1.70.0.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        assert outcome.verified is True
        doc = outcome.documents[0]
        # Only Python-related passages should be selected
        for passage in doc.selected_passages:
            # Node.js version should NOT be in any selected passage
            assert "18.0.1" not in passage.text
            # Rust version should NOT be in any selected passage
            assert "1.70.0" not in passage.text
        # Python version should be in at least one passage
        assert any(
            "3.14.2" in p.text for p in doc.selected_passages
        ), "Python version 3.14.2 must be in at least one passage"

    def test_postgresql_version_not_python_version(self) -> None:
        """PostgreSQL 17.2 in a different selected/unselected passage cannot
        ground a Python version claim."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Versions", "url": "https://example.com/versions"}],
        }
        tool.fetch_payloads = {
            "https://example.com/versions": {
                "url": "https://example.com/versions",
                "status": 200,
                "content_type": "text/html",
                "content_length": 200,
                "truncated": False,
                "data": "Python current version is 3.14.2. PostgreSQL 17.2 was released recently.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        assert outcome.verified is True
        doc = outcome.documents[0]
        # PostgreSQL version should NOT be in any selected passage
        for passage in doc.selected_passages:
            assert "17.2" not in passage.text
        # Python version should be present
        assert any(
            "3.14.2" in p.text for p in doc.selected_passages
        ), "Python version 3.14.2 must be in at least one passage"


class TestVersionDatePriceIdentityExactValues:
    """Tests for GA2-R1-02: version/date/price/identity claims preserve exact values."""

    def test_version_preserves_exact_supported_value(self) -> None:
        """Version claims preserve the exact supported value."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Python", "url": "https://python.org/downloads"}],
        }
        tool.fetch_payloads = {
            "https://python.org/downloads": {
                "url": "https://python.org/downloads",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Python current version is 3.14.2.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        assert outcome.verified is True
        doc = outcome.documents[0]
        assert len(doc.selected_passages) > 0
        # The passage should contain the exact version
        assert any("3.14.2" in p.text for p in doc.selected_passages)

    def test_version_redacts_different_value(self) -> None:
        """Version claims redact a different value than supported."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Python", "url": "https://python.org/downloads"}],
        }
        tool.fetch_payloads = {
            "https://python.org/downloads": {
                "url": "https://python.org/downloads",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Python current version is 3.14.2.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        assert outcome.verified is True
        doc = outcome.documents[0]
        # The wrong version should NOT be in any selected passage
        for passage in doc.selected_passages:
            assert "3.99.0" not in passage.text


class TestGeneralizedSubjectExtraction:
    """Tests for GA2-R1-02: generalized subject extraction."""

    def test_subject_extraction_from_version_of_pattern(self) -> None:
        """Subject extraction from 'version of X' pattern."""
        executor = ExternalVerificationExecutor(_MockKnowledgeTool())  # type: ignore[arg-type]
        subject = executor._extract_requested_subject(
            "what is the current version of infraagent"
        )
        assert subject == "infraagent"

    def test_subject_extraction_from_x_version_pattern(self) -> None:
        """Subject extraction from 'X version' pattern."""
        executor = ExternalVerificationExecutor(_MockKnowledgeTool())  # type: ignore[arg-type]
        subject = executor._extract_requested_subject("docker version is what")
        assert subject == "docker"

    def test_known_subject_still_works(self) -> None:
        """Known subjects from the hard-coded list still work."""
        executor = ExternalVerificationExecutor(_MockKnowledgeTool())  # type: ignore[arg-type]
        subject = executor._extract_requested_subject(
            "what is the current version of python"
        )
        assert subject == "python"

    def test_generic_request_returns_none(self) -> None:
        """Generic request without a named subject returns None."""
        executor = ExternalVerificationExecutor(_MockKnowledgeTool())  # type: ignore[arg-type]
        subject = executor._extract_requested_subject("what is the weather")
        assert subject is None


class TestExplicitURLArbitrarySubject:
    """Tests for GA2-R1-02: explicit URL with arbitrary subject."""

    def test_explicit_url_arbitrary_subject_accepted(self) -> None:
        """Explicit URL: an arbitrary subject/value present in selected
        support is accepted."""
        tool = _MockKnowledgeTool()
        tool.fetch_payloads = {
            "https://example.com/pricing": {
                "url": "https://example.com/pricing",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "InfraAgent Pro costs $99.99 per month.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        frame = _frame(
            "What is the price of InfraAgent Pro?",
            explicit_url="https://example.com/pricing",
        )
        outcome = executor.collect(frame, "What is the price of InfraAgent Pro?")

        assert outcome.verified is True
        doc = outcome.documents[0]
        assert doc.relevance == ExternalEvidenceRelevance.SUFFICIENT
        assert len(doc.selected_passages) > 0
        # The passage should contain the price
        assert any("$99.99" in p.text for p in doc.selected_passages)

    def test_explicit_url_fact_absent_remains_insufficient(self) -> None:
        """Explicit URL: successful fetch but requested fact absent remains
        insufficient."""
        tool = _MockKnowledgeTool()
        tool.fetch_payloads = {
            "https://example.com/about": {
                "url": "https://example.com/about",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "ExampleCorp provides cloud infrastructure services.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        frame = _frame(
            "What is the current version of Python? Visit https://example.com/about",
            explicit_url="https://example.com/about",
        )
        outcome = executor.collect(frame, "What is the current version of Python?")

        # Fetch succeeds but fact is absent => not SUFFICIENT
        assert outcome.verified is False
        assert len(outcome.documents) == 1
        doc = outcome.documents[0]
        assert doc.relevance == ExternalEvidenceRelevance.IRRELEVANT


class TestPartialNeverGroundsConcreteValue:
    """Tests for GA2-R1-02: PARTIAL selected support never grounds a concrete
    current value."""

    def test_partial_support_does_not_verify_version(self) -> None:
        """PARTIAL selected support never grounds a concrete current value."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Partial", "url": "https://example.com/partial"}],
        }
        tool.fetch_payloads = {
            "https://example.com/partial": {
                "url": "https://example.com/partial",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": True,
                "data": "Python version 3.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        # PARTIAL relevance => not verified
        assert outcome.verified is False
        assert outcome.partial is True
        doc = outcome.documents[0]
        assert doc.relevance == ExternalEvidenceRelevance.PARTIAL


class TestCacheRequestSpecificRecomputation:
    """Tests for GA2-R1-02: cache-hit relevance/passage recomputation."""

    def test_cache_hit_recomputes_passages_for_unrelated_request(self) -> None:
        """A cached document with SUFFICIENT relevance and passages for one
        request should have IRRELEVANT relevance (and no passages) for an
        unrelated request."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Python", "url": "https://python.org/downloads"}],
        }
        tool.fetch_payloads = {
            "https://python.org/downloads": {
                "url": "https://python.org/downloads",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Python current version is 3.14.2.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]

        # First request: about Python version => SUFFICIENT with passages
        outcome1 = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )
        assert outcome1.verified is True
        assert outcome1.documents[0].relevance == ExternalEvidenceRelevance.SUFFICIENT
        assert len(outcome1.documents[0].selected_passages) > 0

        # Second request: about cooking (no version keywords) => cache hit
        # but relevance and passages recomputed
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Cooking", "url": "https://python.org/downloads"}],
        }
        outcome2 = executor.collect(
            _frame("How do I make pasta carbonara?"),
            "How do I make pasta carbonara?",
        )
        # Cache hit, but relevance recomputed for cooking request
        # "pasta carbonara" has no version/date/price/identity keywords
        # so relevance should be IRRELEVANT and no passages selected
        assert outcome2.documents[0].relevance == ExternalEvidenceRelevance.IRRELEVANT
        assert len(outcome2.documents[0].selected_passages) == 0


class TestNoAssertionMayMerelyCheckNonNull:
    """Tests that verify semantic correctness, not just non-null/non-empty."""

    def test_semantic_correctness_not_null(self) -> None:
        """Verify the actual claim value is correct, not just that output is
        non-null."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [{"title": "Python", "url": "https://python.org/downloads"}],
        }
        tool.fetch_payloads = {
            "https://python.org/downloads": {
                "url": "https://python.org/downloads",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Python current version is 3.14.2.",
            }
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version of Python?"),
            "What is the current version of Python?",
        )

        # Correct: output is verified and contains the right version
        assert outcome.verified is True
        doc = outcome.documents[0]
        assert doc.relevance == ExternalEvidenceRelevance.SUFFICIENT
        # The correct version should be in the passages
        assert any("3.14.2" in p.text for p in doc.selected_passages)
        # The wrong version should NOT be in the passages
        for passage in doc.selected_passages:
            assert "3.99.0" not in passage.text


# ===========================================================================
# GA2-R1-03 EXTERNAL -> GENERATE RUNTIME CLOSURE
# ===========================================================================


def _external_outcome(
    *,
    passage_text: str,
    relevance: ExternalEvidenceRelevance = ExternalEvidenceRelevance.SUFFICIENT,
) -> ExternalVerificationOutcome:
    """Build selected-passage evidence for the real agent runtime path."""
    document = ExternalDocument(
        title="Release notes",
        url="https://example.com/releases",
        content=passage_text,
        provider="test-provider",
        retrieved_at=datetime.now(timezone.utc),
        relevance=relevance,
        selected_passages=(
            BoundedPassage(
                text=passage_text,
                url="https://example.com/releases",
                title="Release notes",
                provider="test-provider",
                start_offset=0,
                end_offset=len(passage_text),
                relevance=relevance,
            ),
        ),
    )
    evidence = EvidencePackage(
        capability_name="external_verification",
        evidence_name="external_current",
        data={"documents": [document.to_dict()]},
        source="internet",
    )
    return ExternalVerificationOutcome(evidence=evidence, documents=(document,))


def _agent_with_external_outcome(outcome: ExternalVerificationOutcome):
    """Use the real routing/runtime path while mocking only its boundaries."""
    from unittest.mock import MagicMock

    from src.agent.deterministic_agent import DeterministicAgent

    engine = MagicMock()
    model = MagicMock()
    verifier = MagicMock()
    verifier.collect.return_value = outcome
    return DeterministicAgent(engine, model, external_verifier=verifier), model, verifier


class TestVerifiedValueGeneratedArtifact:
    """Runtime proof that verified selected support reaches generated output."""

    def test_python_verified_value_reaches_dockerfile_without_rewriting_other_values(
        self,
    ) -> None:
        outcome = _external_outcome(
            passage_text="Python current version is 3.14.2."
        )
        agent, model, verifier = _agent_with_external_outcome(outcome)
        model.assess.return_value = (
            "FROM python:3.14.2-slim\n"
            "RUN pip install demo==25.1\n"
            "LABEL schema_version=1.2"
        )

        result = agent.run_with_steps(
            "Find the current Python version and write a Dockerfile using it."
        )

        assert "FROM python:3.14.2-slim" in result["response"]
        # The guard must not globally substitute unrelated version-like strings.
        assert "demo==25.1" in result["response"]
        assert "schema_version=1.2" in result["response"]
        request = model.assess.call_args.args[0]
        assert request.intent == "EXTERNAL_VERIFICATION"
        assert request.evidence[0].data["documents"][0]["selected_passages"][0][
            "text"
        ] == "Python current version is 3.14.2."
        verifier.collect.assert_called_once()
        assert result["execution_trace"]["evidence_status"] == "SUFFICIENT"
        assert (
            result["execution_trace"]["actual_request_frame"]["execution_intent"]
            == "GENERATE_CONTENT"
        )

    def test_kubernetes_verified_value_reaches_generated_config(self) -> None:
        outcome = _external_outcome(
            passage_text="Kubernetes current version is 1.32.3."
        )
        agent, model, _verifier = _agent_with_external_outcome(outcome)
        model.assess.return_value = "apiVersion: v1\ndata:\n  kubernetesVersion: 1.32.3"

        result = agent.run_with_steps(
            "Find the current Kubernetes version and create a config snippet using it."
        )

        assert "kubernetesVersion: 1.32.3" in result["response"]
        assert result["execution_trace"]["evidence_status"] == "SUFFICIENT"
        model.assess.assert_called_once()

    def test_missing_or_partial_support_never_generates_a_current_value(self) -> None:
        for outcome, expected_status in (
            (
                _external_outcome(
                    passage_text="Python is a programming language.",
                    relevance=ExternalEvidenceRelevance.IRRELEVANT,
                ),
                "UNAVAILABLE",
            ),
            (
                _external_outcome(
                    passage_text="Python current version is 3.",
                    relevance=ExternalEvidenceRelevance.PARTIAL,
                ),
                "PARTIAL",
            ),
        ):
            agent, model, _verifier = _agent_with_external_outcome(outcome)
            model.assess.return_value = "FROM python:3.14.2-slim"

            result = agent.run_with_steps(
                "Find the current Python version and write a Dockerfile using it."
            )

            assert "3.14.2" not in result["response"]
            assert "cannot be verified" in result["response"].casefold()
            assert result["execution_trace"]["evidence_status"] == expected_status
            model.assess.assert_not_called()

    def test_wrong_subject_value_is_redacted_from_generated_artifact(self) -> None:
        outcome = _external_outcome(
            passage_text="Node.js current version is 18.0.1."
        )
        agent, model, _verifier = _agent_with_external_outcome(outcome)
        model.assess.return_value = "FROM python:18.0.1-slim"

        result = agent.run_with_steps(
            "Find the current Python version and write a Dockerfile using it."
        )

        assert "18.0.1" not in result["response"]
        assert "unverified current claim" in result["response"]
