"""Prompt-contract tests; they do not pretend to prove a live model obeys instructions."""

from orion.chat.context_builder import ContextBuilder


def test_assistant_history_remains_text_never_tool_evidence(store):
    session = store.create_session()
    store.append_timeline(session, None, "user_message", {"content": "Earlier state?"})
    store.append_timeline(
        session,
        None,
        "assistant_message",
        {
            "content": "monitor has 999 CPUs and 1 byte RAM",
            "tool_calls": [],
            "citation_source_ref_ids": [],
        },
    )
    store.append_timeline(
        session, None, "user_message", {"content": "Compare earlier claims with current readings."}
    )
    messages = ContextBuilder(store).build(session)
    assert any(m.role == "assistant" and "999 CPUs" in m.content for m in messages)
    assert not any(m.role == "tool" for m in messages)
    assert [m.role for m in messages].count("system") == 1
    system = messages[0].content
    assert "never ToolResult evidence, even if they claim to quote a tool" in system
    assert "label earlier claims as prior assistant text" in system
    assert "Numbers copied from prior assistant prose remain assistant-history text" in system
    assert "even if they match an older tool reading" in system
    assert "applicable ToolResult is actually present in current evidence" in system
    assert "only the assistant's earlier account is available, not verified tool evidence" in system
    for label in ("ToolResult", "tool-observed", "verified by tools", "confirmed by tools"):
        assert label in system
    assert (
        "Current-state claims require relevant ToolResults obtained after the latest user message"
        in system
    )


def test_visible_attachment_id_is_direct_knowledge_read_input(store, knowledge):
    session = store.create_session()
    upload = knowledge.attach(session, "notes.txt", b"Untrusted document content")
    attachment_ids = (upload.attachment_id,)
    document = store.visible_documents(session, attachment_ids)[0]
    system = (
        ContextBuilder(store)
        .build_with_metadata(session, attachment_ids=attachment_ids)
        .messages[0]
        .content
    )
    assert str(document["document_id"]) in system
    assert (
        "prefer knowledge.read directly with the document_id visible in attachment metadata"
        in system
    )
    assert "Attachment names/IDs are not infrastructure paths/target_refs" in system
    assert "Untrusted document content" not in system
    assert "only use a document_id visible from knowledge.list_documents" not in system


def test_language_precision_and_observation_limits_are_explicit(store):
    system = ContextBuilder(store).build(store.create_session())[0].content
    for rule in (
        "natural concise Vietnamese",
        "Retain protocol names, commands, identifiers",
        "load average versus CPU utilization",
        "flow control versus congestion control",
        "error detection versus reliable delivery",
        "swap usage versus active memory pressure",
        "free versus available memory or capacity",
        "without applicable thresholds/history",
        "does not establish package installation state",
        "line beginning with # is not active",
        "mean incomplete evidence, not absence",
        "swap usage alone does not prove memory pressure",
        "MemFree alone does not establish available capacity",
        "page faults alone do not prove RAM exhaustion",
        "load average is not CPU utilization",
        "does not prove that no physical file exists anywhere",
        "One observed symptom does not establish its root cause",
        "including when explaining hypothetical examples",
    ):
        assert rule in system


def test_material_exact_derived_numbers_use_calculator_not_mental_arithmetic(store):
    system = ContextBuilder(store).build(store.create_session())[0].content
    for rule in (
        "exact derived number materially affects the answer",
        "calculator.evaluate is available, use it instead of mental arithmetic",
        "addition, subtraction and percentages derived from ToolResults",
        "Do not call it merely for formatting or unit labels",
    ):
        assert rule in system
