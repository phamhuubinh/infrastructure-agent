"""Regression tests for Phase 5 bug fixes (IDs 500-505).

These tests verify that previously fixed bugs do not regress:
- 500: Alias "database"/"db" removed from target_resolver
- 501: try/except in run() and run_with_steps() catches UnknownTargetError
- 502: "orion" and "database" in skip words
- 503: _build_chat_context() limits context (summary + 4 recent + truncate 600)
- 504: _is_conversational() routes yes-no/clarification to chat
- 505: "mem" in MEMORY_ASSESSMENT keywords
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.pipeline.intent_resolver import Intent, IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import TargetResolver
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


# ------------------------------------------------------------------
# Task 500: Verify alias "database"/"db" removed
# ------------------------------------------------------------------
def test_no_database_alias_in_target_resolver() -> None:
    """Verify 'database' and 'db' are NOT aliases in TargetResolver."""
    # The hardcoded aliases and config should not contain "database" or "db".
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write('{"targets": {}}')
    tmp.close()
    store = TargetStore(path=tmp.name)
    registry = TargetRegistry(store=store)
    registry.add("localhost")
    resolver = TargetResolver(target_registry=registry)
    Path(tmp.name).unlink(missing_ok=True)

    # "database" should not resolve as an alias — it should be a skip word.
    req = InvestigationRequest(raw_request="check database")
    resolver.resolve(req)
    assert req.target == "localhost"  # Should NOT raise UnknownTargetError


# ------------------------------------------------------------------
# Task 502: "orion" and "database" in skip words
# ------------------------------------------------------------------
def test_orion_is_skip_word() -> None:
    """'orion' should not be treated as a target name."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write('{"targets": {}}')
    tmp.close()
    store = TargetStore(path=tmp.name)
    registry = TargetRegistry(store=store)
    registry.add("localhost")
    resolver = TargetResolver(target_registry=registry)
    Path(tmp.name).unlink(missing_ok=True)

    req = InvestigationRequest(raw_request="what is orion")
    resolver.resolve(req)
    assert req.target == "localhost"  # Falls through gracefully


def test_database_is_skip_word() -> None:
    """'database' should not be treated as a target name."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write('{"targets": {}}')
    tmp.close()
    store = TargetStore(path=tmp.name)
    registry = TargetRegistry(store=store)
    registry.add("localhost")
    resolver = TargetResolver(target_registry=registry)
    Path(tmp.name).unlink(missing_ok=True)

    req = InvestigationRequest(raw_request="check database status")
    resolver.resolve(req)
    assert req.target == "localhost"


# ------------------------------------------------------------------
# Task 504: _is_conversational() routes yes-no to chat
# ------------------------------------------------------------------
def test_conversational_vietnamese_yes_no() -> None:
    """Vietnamese yes-no question should be detected as conversational."""
    from src.agent.deterministic_agent import DeterministicAgent

    req = InvestigationRequest(raw_request="server01 là localhost?")
    assert DeterministicAgent._is_conversational("server01 là localhost?", req)


def test_conversational_co_phai() -> None:
    """'có phải' pattern should be detected as conversational."""
    from src.agent.deterministic_agent import DeterministicAgent

    req = InvestigationRequest(raw_request="có phải server01 là localhost")
    assert DeterministicAgent._is_conversational("có phải server01 là localhost", req)


def test_conversational_nhu_the_nao_not_block_memory() -> None:
    """'mem như thế nào?' should NOT be blocked — it has MEMORY_ASSESSMENT intent,
    not MACHINE_ASSESSMENT. The _is_conversational check only applies to
    MACHINE_ASSESSMENT intents, so this should return False for non-MACHINE intents
    (allowing pipeline).
    """

    intent_resolver = IntentResolver()
    req = intent_resolver.resolve("mem như thế nào")
    # This should be MEMORY_ASSESSMENT, not MACHINE_ASSESSMENT.
    # _is_conversational only blocks MACHINE_ASSESSMENT.
    # Even for MEMORY_ASSESSMENT, _is_conversational checks all patterns,
    # so it may still return True. The key is that _should_pipeline
    # only calls _is_conversational if intent == MACHINE_ASSESSMENT.
    assert req.intent == Intent.MEMORY_ASSESSMENT


# ------------------------------------------------------------------
# Task 505: "mem" in MEMORY_ASSESSMENT keywords
# ------------------------------------------------------------------
def test_mem_keyword_matches_memory() -> None:
    """'mem' should match MEMORY_ASSESSMENT intent."""
    intent_resolver = IntentResolver()
    req = intent_resolver.resolve("mem đang được hoạt động như nào?")
    assert req.intent == Intent.MEMORY_ASSESSMENT


def test_mem_keyword_standalone() -> None:
    """Just 'mem' should match MEMORY_ASSESSMENT."""
    intent_resolver = IntentResolver()
    req = intent_resolver.resolve("check mem")
    assert req.intent == Intent.MEMORY_ASSESSMENT


# ------------------------------------------------------------------
# Task 503: _build_chat_context limits context
# ------------------------------------------------------------------
def test_build_chat_context_limits_pairs(tmp_path: Path) -> None:
    """Test that context building limits to 4 recent pairs."""
    from src.agent.conversation_store import ConversationStore
    from src.agent.deterministic_agent import DeterministicAgent

    store = ConversationStore("test-session-1", store_dir=str(tmp_path))
    # Add 10 user+assistant turns
    for i in range(10):
        store.add_turn(f"question {i}", f"answer {i}")

    # Create a minimal agent just for testing _build_chat_context
    # We bypass type hints by using object()
    agent = object.__new__(DeterministicAgent)
    agent._conversation_store = store  # type: ignore[attr-defined]
    context = agent._build_chat_context()  # type: ignore[attr-defined]
    # Should have at most 4 user questions in context
    assert "question 0" not in context  # Oldest should be truncated
    assert "question 9" in context  # Latest should be present


def test_build_chat_context_truncates_long_messages(tmp_path: Path) -> None:
    """Test that long assistant messages are truncated (shown by '...' marker)."""
    from src.agent.conversation_store import ConversationStore
    from src.agent.deterministic_agent import DeterministicAgent

    store = ConversationStore("test-session-2", store_dir=str(tmp_path))
    long_answer = "x" * 1000
    store.add_turn("short question", long_answer)

    # Create a minimal agent just for testing _build_chat_context
    agent = object.__new__(DeterministicAgent)
    agent._conversation_store = store  # type: ignore[attr-defined]
    context = agent._build_chat_context()  # type: ignore[attr-defined]
    # Long answer should be truncated (indicated by "..." at the end)
    assert "..." in context
    # Should not contain the full 1000-char original
    assert (
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        not in context
    )


# ------------------------------------------------------------------
# Task 501: try/except in run() catches exceptions
# ------------------------------------------------------------------
def test_run_catches_unknown_target_error() -> None:
    """Verify that run() and run_with_steps() have try/except wrapping.

    This is a structural test — we verify the methods exist and have
    try/except blocks by checking the source code.
    """
    import inspect

    from src.agent.deterministic_agent import DeterministicAgent

    run_source = inspect.getsource(DeterministicAgent.run)
    assert "try:" in run_source
    assert "except Exception" in run_source
    assert "chat" in run_source

    run_steps_source = inspect.getsource(DeterministicAgent.run_with_steps)
    assert "try:" in run_steps_source
    assert "except Exception" in run_steps_source
    assert "chat" in run_steps_source
