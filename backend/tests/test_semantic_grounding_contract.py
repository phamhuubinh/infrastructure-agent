"""Prompt-contract tests; they do not pretend to prove a live model obeys instructions."""

from orion.chat.context_builder import ContextBuilder
from orion.contracts import RuntimeScope, ToolCall
from orion.tool_runtime.calculator import calculate
from orion.tool_runtime.infrastructure import infrastructure_definitions


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
    assert "are conversation text, not verified ToolResults" in system
    assert "even exact quotes or numbers attributed to tools" in system
    assert "When only prior assistant text supports a claim, label it as such" in system
    assert "Current claims require results obtained after the latest user message" in system


def test_attachment_metadata_exposes_exact_id_without_prefetching_content(store, knowledge):
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
    assert "Current session attachments" in system
    assert str(document["document_id"]) in system
    assert "name=notes.txt" in system
    assert "media_type=text/plain" in system
    assert "use knowledge.search directly, or knowledge.read" in system
    assert "exact attachment document_id is visible" in system
    assert "names/IDs are not filesystem paths or target_refs" in system
    assert "Untrusted document content" not in system


def test_language_precision_and_observation_limits_are_explicit(store):
    system = ContextBuilder(store).build(store.create_session())[0].content
    for rule in (
        "natural Vietnamese",
        "preserve technical identifiers",
        "load average distinct from CPU utilization",
        "flow control from congestion control",
        "error detection from delivery",
        "swap occupancy from pressure",
        "free from available memory",
        "A commented setting is inactive",
        "mean incomplete evidence",
        "Point-in-time readings alone do not establish",
        "health, capacity, contention, RAM exhaustion, or root cause",
        "hypothetical mechanisms as uncertain",
    ):
        assert rule in system


def test_material_exact_derived_numbers_use_calculator_not_mental_arithmetic(store):
    system = ContextBuilder(store).build(store.create_session())[0].content
    for rule in (
        "calculator.evaluate for consequential exact arithmetic",
        "derived sums, differences and percentages",
        "never just for formatting or unit labels",
        "requested arithmetic, round sensibly",
        "use $...$ for TeX and plain commas in prose",
    ):
        assert rule in system


def test_linux_file_tools_require_explicit_configured_target_paths() -> None:
    definitions = {definition.name: definition for definition in infrastructure_definitions()}
    read = definitions["linux.file.read"]
    assert "explicit path on a configured Linux infrastructure target" in read.description
    assert "Never use for Orion session attachments or Project documents" in read.description
    assert read.input_schema["required"] == ["target_ref", "path"]
    assert definitions["linux.document.read"].input_schema["required"] == ["target_ref", "path"]


def test_calculator_remains_authoritative_for_requested_arithmetic() -> None:
    result = calculate(
        ToolCall(
            call_id="arithmetic",
            tool_name="calculator.evaluate",
            arguments={"expression": "1589 * 3324 / 72"},
            runtime_scope=RuntimeScope(
                session_id="session", principal_id="local", workspace_id="local"
            ),
        )
    )
    assert result.status == "success"
    assert result.data["value"] == 73_358.83333333333
    assert f"{result.data['value']:,.2f}" == "73,358.83"
