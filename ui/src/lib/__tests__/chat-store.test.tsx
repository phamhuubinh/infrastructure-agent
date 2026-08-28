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
      <button onClick={() => void chat.renameSession(sessionId, "My custom title")}>rename</button>
      <button onClick={() => chat.addOptimisticMessage(sessionId, "First message")}>message</button>
      <span>{chat.sessions[0]?.messages.map((message) => message.content).join("|")}</span>
      <span data-testid="project-id">{chat.sessions[0]?.projectId || "none"}</span>
      <span data-testid="session-count">{chat.sessions.length}</span>
      <span data-testid="title">
        {chat.sessions.find((session) => session.id === sessionId)?.title}
      </span>
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

function assistantTimelineItem(content: string, toolCalls: unknown[] = []): TimelineItem {
  return {
    item_id: "assistant-1",
    session_id: "session-1",
    created_at: "2026-08-28T00:00:01Z",
    kind: "assistant_message",
    payload: { content, tool_calls: toolCalls },
    call_id: null,
    tool_name: null,
  };
}

describe("M1 session store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });
  it("creates sessions through the current API without browser session storage", async () => {
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/sessions" && !init?.method) return Promise.resolve(jsonResponse([]));
      if (path === "/api/sessions")
        return Promise.resolve(jsonResponse({ session_id: "session-1" }));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <Harness />
      </ChatProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "create" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/sessions", expect.anything()));
    expect(window.localStorage.length).toBe(0);
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

  it("keeps a canonical custom title through rename and timeline hydration", async () => {
    const timeline: TimelineItem[] = [
      {
        item_id: "u1",
        session_id: "session-1",
        created_at: "now",
        kind: "user_message",
        payload: { content: "Original question" },
        call_id: null,
        tool_name: null,
      },
    ];
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/sessions" && !init?.method)
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "session-1",
              project_id: null,
              custom_title: null,
              title: "Original question",
              created_at: "now",
              last_activity_at: "now",
            },
          ]),
        );
      if (path === "/api/sessions/session-1" && init?.method === "PATCH")
        return Promise.resolve(
          jsonResponse({
            session_id: "session-1",
            project_id: null,
            custom_title: "My custom title",
            title: "My custom title",
          }),
        );
      if (path === "/api/sessions/session-1")
        return Promise.resolve(
          jsonResponse({
            session_id: "session-1",
            project_id: null,
            custom_title: "My custom title",
          }),
        );
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

    await screen.findByText("Original question");
    fireEvent.click(screen.getByRole("button", { name: "rename" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toBe("My custom title"));
    fireEvent.click(screen.getByRole("button", { name: "load" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toBe("My custom title"));
  });

  it("preserves a custom title for an empty session's first message", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions")
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "session-1",
              project_id: null,
              custom_title: "Pinned",
              title: "Pinned",
              created_at: "now",
              last_activity_at: "now",
            },
            {
              session_id: "automatic",
              project_id: null,
              custom_title: null,
              title: "New chat",
              created_at: "now",
              last_activity_at: "now",
            },
          ]),
        );
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ChatProvider>
        <Harness />
      </ChatProvider>,
    );
    await screen.findByText("Pinned");
    fireEvent.click(screen.getByRole("button", { name: "message" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toBe("Pinned"));
  });

  it("updates an unrenamed empty session title from its first message", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions")
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "automatic",
              project_id: null,
              custom_title: null,
              title: "New chat",
              created_at: "now",
              last_activity_at: "now",
            },
          ]),
        );
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ChatProvider>
        <Harness sessionId="automatic" />
      </ChatProvider>,
    );
    await screen.findByText("New chat");
    fireEvent.click(screen.getByRole("button", { name: "message" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toBe("First message"));
  });

  it("keeps a Project conversation custom title during timeline hydration", () => {
    const hydrated = sessionFromTimeline(
      "project-session",
      [
        {
          item_id: "u1",
          session_id: "project-session",
          created_at: "now",
          kind: "user_message",
          payload: { content: "Derived Project title" },
          call_id: null,
          tool_name: null,
        },
      ],
      [],
      "project-a",
      "Pinned Project title",
    );
    expect(hydrated).toMatchObject({
      projectId: "project-a",
      title: "Pinned Project title",
      customTitle: "Pinned Project title",
    });
  });

  it("does not project an empty assistant tool-call turn as a chat message", () => {
    const item = assistantTimelineItem("", [{ id: "call-1", name: "calculator.evaluate" }]);

    expect(assistantMessageFromTimelineItem(item)).toBeNull();
    expect(sessionFromTimeline("session-1", [item]).messages).toEqual([]);
    expect(sessionFromTimeline("session-1", [item]).timeline).toEqual([item]);
  });

  it("does not project a whitespace-only assistant tool-call turn as a chat message", () => {
    const item = assistantTimelineItem("\n\n", [{ id: "call-1", name: "calculator.evaluate" }]);

    expect(assistantMessageFromTimelineItem(item)).toBeNull();
    expect(sessionFromTimeline("session-1", [item]).messages).toEqual([]);
  });

  it("preserves visible assistant text when the turn also contains tool calls", () => {
    const item = assistantTimelineItem("I will check that.", [
      { id: "call-1", name: "calculator.evaluate" },
    ]);

    expect(assistantMessageFromTimelineItem(item)).toMatchObject({
      itemId: "assistant-1",
      role: "assistant",
      content: "I will check that.",
    });
  });

  it("keeps ordinary assistant text unchanged", () => {
    const item = assistantTimelineItem("Ordinary assistant response.");

    expect(assistantMessageFromTimelineItem(item)).toMatchObject({
      itemId: "assistant-1",
      role: "assistant",
      content: "Ordinary assistant response.",
    });
  });

  it("hydrates the canonical project identity and reopens the existing Project session", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions") {
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "project-session",
              project_id: "project-a",
              title: "Keep this project timeline",
              created_at: "2026-08-25T00:00:00Z",
              last_activity_at: "2026-08-25T00:00:02Z",
            },
          ]),
        );
      }
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

    await waitFor(() => expect(screen.getByTestId("session-count").textContent).toBe("1"));
    fireEvent.click(screen.getByRole("button", { name: "load" }));
    await waitFor(() => expect(screen.getByTestId("project-id").textContent).toBe("project-a"));
    expect(screen.getByTestId("project-id").textContent).toBe("project-a");
    expect(screen.getByTestId("citations").textContent).toBe("project-source");
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/project-session"),
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/project-session/timeline"),
    ).toHaveLength(1);
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

  it("restores safe infrastructure activity and SourceRef metadata from the canonical timeline", () => {
    const session = sessionFromTimeline("session-1", [
      {
        item_id: "call",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:00Z",
        kind: "tool_call",
        payload: { arguments: { target_ref: "monitor" }, operation_kind: "read" },
        call_id: "infra-1",
        tool_name: "linux.system.inspect",
      },
      {
        item_id: "result",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:01Z",
        kind: "tool_result",
        payload: {
          result: {
            status: "error",
            error: { code: "outcome_unknown" },
            data: { target_ref: "monitor", changed: true, verification: { status: "unknown" } },
            sources: [],
          },
        },
        call_id: "infra-1",
        tool_name: "linux.system.inspect",
      },
      {
        item_id: "source-result",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:02Z",
        kind: "tool_result",
        payload: {
          result: {
            status: "success",
            sources: [
              {
                source_ref_id: "linux-source",
                source_kind: "linux",
                source_id: "monitor",
                label: "Monitor",
                section: "system.inspect",
                retrieved_at: "2026-08-25T00:00:01Z",
              },
            ],
          },
        },
        call_id: "source-1",
        tool_name: "linux.system.inspect",
      },
      {
        item_id: "restart-call",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:03Z",
        kind: "tool_call",
        payload: { arguments: { target_ref: "monitor" }, operation_kind: "mutation" },
        call_id: "restart-1",
        tool_name: "linux.service.restart",
      },
      {
        item_id: "restart-result",
        session_id: "session-1",
        created_at: "2026-08-25T00:00:04Z",
        kind: "tool_result",
        payload: {
          result: {
            status: "success",
            data: { target_ref: "monitor", changed: true, verification: { status: "verified" } },
            sources: [],
          },
        },
        call_id: "restart-1",
        tool_name: "linux.service.restart",
      },
    ]);

    expect(session.activity).toContainEqual({
      callId: "infra-1",
      toolName: "linux.system.inspect",
      status: "started",
      targetRef: "monitor",
      operationKind: "read",
    });
    expect(session.activity).toContainEqual({
      callId: "infra-1",
      toolName: "linux.system.inspect",
      status: "failed",
      targetRef: "monitor",
      operationKind: "read",
      changed: true,
      verification: "unknown",
      outcomeUnknown: true,
    });
    expect(session.activity).toContainEqual({
      callId: "restart-1",
      toolName: "linux.service.restart",
      status: "started",
      targetRef: "monitor",
      operationKind: "mutation",
    });
    expect(session.activity).toContainEqual({
      callId: "restart-1",
      toolName: "linux.service.restart",
      status: "completed",
      targetRef: "monitor",
      operationKind: "mutation",
      changed: true,
      verification: "verified",
    });
    expect(session.sources).toContainEqual({
      sourceRefId: "linux-source",
      sourceKind: "linux",
      documentId: null,
      segmentId: null,
      page: null,
      section: "system.inspect",
      label: "Monitor",
      url: null,
      retrievedAt: "2026-08-25T00:00:01Z",
    });
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
