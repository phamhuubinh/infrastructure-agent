import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ChatProvider,
  assistantMessageFromTimelineItem,
  sessionFromTimeline,
  sessionRoute,
  useChat,
  type SessionDocument,
  type TimelineItem,
} from "@/lib/chat-store";

function Harness({ sessionId = "session-1" }: { sessionId?: string }) {
  const chat = useChat();
  return (
    <div>
      <button onClick={() => void chat.createSession()}>create</button>
      <button onClick={() => void chat.switchSession(sessionId)}>load</button>
      <span>{chat.sessions[0]?.messages.map((message) => message.content).join("|")}</span>
      <span data-testid="project-id">{chat.sessions[0]?.projectId || "none"}</span>
      <span data-testid="session-count">{chat.sessions.length}</span>
      <span data-testid="citations">
        {chat.sessions[0]?.messages.at(-1)?.citationSourceRefIds?.join("|") || "none"}
      </span>
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
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });
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
    const timeline: TimelineItem[] = [
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
    ];
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions/session-1") {
        return Promise.resolve(jsonResponse({ session_id: "session-1", project_id: null }));
      }
      if (path === "/api/sessions/session-1/timeline")
        return Promise.resolve(jsonResponse(timeline));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <Harness />
      </ChatProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "load" }));

    await screen.findByText("Hello|Hi");
    expect(fetchMock).toHaveBeenCalledWith("/api/sessions/session-1", expect.anything());
    expect(fetchMock).toHaveBeenCalledWith("/api/sessions/session-1/timeline", expect.anything());
  });

  it("hydrates the canonical project identity and reopens the existing Project session", async () => {
    window.localStorage.setItem("orion-m1-session-ids", JSON.stringify(["project-session"]));
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions/project-session") {
        return Promise.resolve(
          jsonResponse({ session_id: "project-session", project_id: "project-a" }),
        );
      }
      if (path === "/api/sessions/project-session/timeline") {
        return Promise.resolve(
          jsonResponse([
            {
              item_id: "u1",
              session_id: "project-session",
              created_at: "2026-08-25T00:00:00Z",
              kind: "user_message",
              payload: { content: "Keep this project timeline" },
              call_id: null,
              tool_name: null,
            },
            {
              item_id: "search",
              session_id: "project-session",
              created_at: "2026-08-25T00:00:01Z",
              kind: "tool_result",
              payload: {
                result: {
                  status: "success",
                  sources: [
                    {
                      source_ref_id: "project-source",
                      source_kind: "project",
                      source_id: "project-a",
                      document_id: "project-doc",
                      segment_id: "segment-a",
                    },
                  ],
                },
              },
              call_id: "search",
              tool_name: "knowledge.search",
            },
            {
              item_id: "answer",
              session_id: "project-session",
              created_at: "2026-08-25T00:00:02Z",
              kind: "assistant_message",
              payload: {
                content: "Project-grounded answer.",
                citation_source_ref_ids: ["project-source"],
              },
              call_id: null,
              tool_name: null,
            },
          ]),
        );
      }
      if (path === "/api/projects/project-a/documents") {
        return Promise.resolve(
          jsonResponse([
            {
              document: {
                document_id: "project-doc",
                source: { kind: "project", source_id: "project-a" },
                name: "requirements.md",
                media_type: "text/markdown",
              },
              attachment_id: "project-upload",
              status: "ready",
              error_message: null,
              ingestion: [],
            },
          ]),
        );
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <Harness sessionId="project-session" />
      </ChatProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("project-id").textContent).toBe("project-a"));
    expect(screen.getByTestId("project-id").textContent).toBe("project-a");
    expect(screen.getByTestId("citations").textContent).toBe("project-source");
    fireEvent.click(screen.getByRole("button", { name: "load" }));
    await waitFor(() => expect(screen.getByTestId("session-count").textContent).toBe("1"));
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/project-session"),
    ).toHaveLength(2);
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/project-session/timeline"),
    ).toHaveLength(2);
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

  it("keeps Internet citations only when a canonical Internet source was returned", () => {
    const session = sessionFromTimeline("session-1", [
      {
        item_id: "tool-result",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:00Z",
        kind: "tool_result" as const,
        call_id: "internet-1",
        tool_name: "internet.search",
        payload: {
          result: {
            status: "success",
            sources: [
              {
                source_ref_id: "internet-source",
                source_kind: "internet",
                source_id: "https://example.test/article",
                document_id: null,
                segment_id: null,
                page: null,
                section: null,
                label: "Example article",
                url: "https://example.test/article",
                retrieved_at: "2026-08-25T00:00:00Z",
              },
            ],
          },
        },
      },
      {
        item_id: "assistant",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:01Z",
        kind: "assistant_message" as const,
        call_id: null,
        tool_name: null,
        payload: {
          content: "Grounded.",
          citation_source_ref_ids: ["internet-source", "invented"],
        },
      },
    ]);

    expect(session.sources).toEqual([
      expect.objectContaining({
        sourceRefId: "internet-source",
        sourceKind: "internet",
        documentId: null,
        url: "https://example.test/article",
      }),
    ]);
    expect(session.messages[0].citationSourceRefIds).toEqual(["internet-source"]);
  });

  it("keeps ready Project citations and hides unavailable Project citations", () => {
    const projectDocument: SessionDocument = {
      document: {
        document_id: "project-doc",
        source: { kind: "project", source_id: "project-a" },
        name: "requirements.md",
        media_type: "text/markdown",
      },
      attachmentId: "project-upload",
      status: "ready",
      errorMessage: null,
      ingestion: [],
    };
    const timeline: TimelineItem[] = [
      {
        item_id: "result",
        session_id: "project-session",
        created_at: "2026-08-25T00:00:00Z",
        kind: "tool_result" as const,
        payload: {
          result: {
            status: "success",
            sources: [
              {
                source_ref_id: "project-source",
                source_kind: "project",
                source_id: "project-a",
                document_id: "project-doc",
                segment_id: "segment-a",
              },
            ],
          },
        },
        call_id: "search",
        tool_name: "knowledge.search",
      },
      {
        item_id: "answer",
        session_id: "project-session",
        created_at: "2026-08-25T00:00:01Z",
        kind: "assistant_message" as const,
        payload: {
          content: "Grounded answer.",
          citation_source_ref_ids: ["project-source", "invented"],
        },
        call_id: null,
        tool_name: null,
      },
    ];

    const ready = sessionFromTimeline("project-session", timeline, [projectDocument], "project-a");
    const unavailable = sessionFromTimeline(
      "project-session",
      timeline,
      [{ ...projectDocument, status: "failed" }],
      "project-a",
    );

    expect(ready.messages[0].citationSourceRefIds).toEqual(["project-source"]);
    expect(unavailable.messages[0].citationSourceRefIds).toEqual([]);
  });

  it("preserves canonical Project citation IDs when reconciling a completed assistant event", () => {
    const message = assistantMessageFromTimelineItem({
      item_id: "answer",
      session_id: "project-session",
      created_at: "2026-08-25T00:00:01Z",
      kind: "assistant_message",
      payload: { content: "Grounded.", citation_source_ref_ids: ["project-source"] },
      call_id: null,
      tool_name: null,
    });

    expect(message?.citationSourceRefIds).toEqual(["project-source"]);
  });

  it("maps normal and Project A/B sessions to their route-owned destinations", () => {
    expect(sessionRoute({ projectId: null })).toEqual({ to: "/" });
    expect(sessionRoute({ projectId: "project-a" })).toEqual({
      to: "/projects/$projectId",
      params: { projectId: "project-a" },
    });
    expect(sessionRoute({ projectId: "project-b" })).toEqual({
      to: "/projects/$projectId",
      params: { projectId: "project-b" },
    });
  });
});
