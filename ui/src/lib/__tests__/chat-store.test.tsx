import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatProvider, sessionFromTimeline, useChat, type SessionDocument } from "@/lib/chat-store";

function Harness() {
  const chat = useChat();
  return (
    <div>
      <button onClick={() => void chat.createSession()}>create</button>
      <button onClick={() => void chat.switchSession("session-1")}>load</button>
      <span>{chat.sessions[0]?.messages.map((message) => message.content).join("|")}</span>
    </div>
  );
}

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("M1 session store", () => {
  it("creates sessions through the current API and remembers only the opaque session ID", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ session_id: "session-1" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <Harness />
      </ChatProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "create" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/sessions", expect.anything()));
    expect(JSON.parse(window.localStorage.getItem("orion-m1-session-ids") || "[]")).toEqual([
      "session-1",
    ]);
  });

  it("reconstructs messages from the canonical per-session timeline", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        {
          item_id: "u1",
          session_id: "session-1",
          created_at: "2026-08-24T00:00:00Z",
          kind: "user_message",
          payload: { content: "Hello" },
          call_id: null,
          tool_name: null,
        },
        {
          item_id: "a1",
          session_id: "session-1",
          created_at: "2026-08-24T00:00:01Z",
          kind: "assistant_message",
          payload: { content: "Hi" },
          call_id: null,
          tool_name: null,
        },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <Harness />
      </ChatProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "load" }));

    await screen.findByText("Hello|Hi");
    expect(fetchMock).toHaveBeenCalledWith("/api/sessions/session-1/timeline", expect.anything());
  });

  it("keeps only currently available canonical sources, including distinct cross-document identity", () => {
    const documents: SessionDocument[] = [
      {
        document: {
          document_id: "doc-a",
          source: { kind: "session", source_id: "session-1" },
          name: "alpha.md",
          media_type: "text/markdown",
        },
        attachmentId: "attach-a",
        status: "ready",
        errorMessage: null,
        ingestion: [],
      },
      {
        document: {
          document_id: "doc-b",
          source: { kind: "session", source_id: "session-1" },
          name: "beta.md",
          media_type: "text/markdown",
        },
        attachmentId: "attach-b",
        status: "ready",
        errorMessage: null,
        ingestion: [],
      },
    ];
    const session = sessionFromTimeline(
      "session-1",
      [
        {
          item_id: "read-result",
          session_id: "session-1",
          created_at: "2026-08-25T00:00:00Z",
          kind: "tool_result",
          payload: {
            result: {
              status: "success",
              sources: [
                {
                  source_ref_id: "source-a",
                  source_kind: "session",
                  source_id: "session-1",
                  document_id: "doc-a",
                  segment_id: "segment-a",
                  page: 2,
                  section: "Overview",
                },
                {
                  source_ref_id: "source-b",
                  source_kind: "session",
                  source_id: "session-1",
                  document_id: "doc-b",
                  segment_id: "segment-b",
                  page: null,
                  section: "Comparison",
                },
              ],
            },
          },
          call_id: "read-1",
          tool_name: "knowledge.read",
        },
        {
          item_id: "answer",
          session_id: "session-1",
          created_at: "2026-08-25T00:00:01Z",
          kind: "assistant_message",
          payload: {
            content: "Whole-document comparison.",
            citation_source_ref_ids: ["source-a", "source-b", "invented"],
          },
          call_id: null,
          tool_name: null,
        },
      ],
      documents,
    );

    expect(session.activity).toEqual([
      { callId: "read-1", toolName: "knowledge.read", status: "completed" },
    ]);
    expect(session.sources.map((source) => [source.sourceRefId, source.label])).toEqual([
      ["source-a", "alpha.md"],
      ["source-b", "beta.md"],
    ]);
    expect(session.messages[0].citationSourceRefIds).toEqual(["source-a", "source-b"]);
  });
});
