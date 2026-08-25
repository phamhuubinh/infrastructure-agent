import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatProvider } from "@/lib/chat-store";
import { ChatPage, parseSseEvents } from "@/routes/index";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(events: unknown[]): Response {
  return new Response(events.map((event) => "data: " + JSON.stringify(event) + "\n\n").join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });
}

function renderChat() {
  return render(
    <ChatProvider>
      <ChatPage />
    </ChatProvider>,
  );
}

describe("M1 Chat integration", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("parses complete SSE frames and retains an incomplete final frame", () => {
    const first = JSON.stringify({ type: "tool.started", created_at: "now", payload: {} });
    const second = JSON.stringify({ type: "tool.completed", created_at: "now", payload: {} });
    const parsed = parseSseEvents("data: " + first + "\n\ndata: " + second);
    expect(parsed.events).toHaveLength(1);
    expect(parsed.events[0].type).toBe("tool.started");
    expect(parsed.remainder).toContain("tool.completed");
  });

  it("creates a session, submits a direct message over SSE, and renders the reloaded final assistant answer", async () => {
    const fetchMock = vi.fn(async (path: string, _init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions") return jsonResponse({ session_id: "chat-1" }, 201);
      if (path === "/api/sessions/chat-1/messages/stream") {
        return sseResponse([
          {
            type: "request.accepted",
            created_at: "now",
            payload: { request_id: "req-1", session_id: "chat-1" },
          },
          { type: "model.started", created_at: "now", payload: {} },
          { type: "assistant.delta", created_at: "now", payload: { content: "Hello " } },
          { type: "assistant.delta", created_at: "now", payload: { content: "from M1." } },
          { type: "model.completed", created_at: "now", payload: { tool_call_count: 0 } },
          {
            type: "assistant.message",
            created_at: "now",
            payload: {
              content: "Hello from M1.",
              item: {
                item_id: "a1",
                session_id: "chat-1",
                created_at: "2026-08-24T00:00:01Z",
                kind: "assistant_message",
                payload: { content: "Hello from M1." },
                call_id: null,
                tool_name: null,
              },
            },
          },
          { type: "request.completed", created_at: "now", payload: {} },
        ]);
      }
      if (path === "/api/sessions/chat-1/timeline") {
        return jsonResponse([
          {
            item_id: "u1",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:00Z",
            kind: "user_message",
            payload: { content: "Hello Orion" },
            call_id: null,
            tool_name: null,
          },
          {
            item_id: "a1",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:01Z",
            kind: "assistant_message",
            payload: { content: "Hello from M1." },
            call_id: null,
            tool_name: null,
          },
        ]);
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    await screen.findByRole("textbox", { name: "Chat input" });
    fireEvent.change(screen.getByRole("textbox", { name: "Chat input" }), {
      target: { value: "Hello Orion" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("Hello from M1.");
    expect(screen.getAllByText("Hello from M1.")).toHaveLength(1);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/models",
      "/api/sessions",
      "/api/sessions/chat-1/messages/stream",
      "/api/sessions/chat-1/timeline",
    ]);
  });

  it("presents calculator tool started/completed activity after the canonical timeline reload", async () => {
    const fetchMock = vi.fn(async (path: string, _init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions") return jsonResponse({ session_id: "chat-1" }, 201);
      if (path === "/api/sessions/chat-1/messages/stream") {
        return sseResponse([
          {
            type: "request.accepted",
            created_at: "now",
            payload: { request_id: "req-1", session_id: "chat-1" },
          },
          {
            type: "tool.started",
            created_at: "now",
            payload: { call_id: "calc-1", tool_name: "calculator.evaluate" },
          },
          {
            type: "tool.completed",
            created_at: "now",
            payload: { call_id: "calc-1", tool_name: "calculator.evaluate", status: "success" },
          },
          { type: "request.completed", created_at: "now", payload: {} },
        ]);
      }
      if (path === "/api/sessions/chat-1/timeline") {
        return jsonResponse([
          {
            item_id: "u1",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:00Z",
            kind: "user_message",
            payload: { content: "What is 2 + 2?" },
            call_id: null,
            tool_name: null,
          },
          {
            item_id: "t1",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:01Z",
            kind: "tool_call",
            payload: { arguments: { expression: "2 + 2" } },
            call_id: "calc-1",
            tool_name: "calculator.evaluate",
          },
          {
            item_id: "t2",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:02Z",
            kind: "tool_result",
            payload: { result: { status: "success", data: { value: 4 } } },
            call_id: "calc-1",
            tool_name: "calculator.evaluate",
          },
          {
            item_id: "a1",
            session_id: "chat-1",
            created_at: "2026-08-24T00:00:03Z",
            kind: "assistant_message",
            payload: { content: "The answer is 4." },
            call_id: null,
            tool_name: null,
          },
        ]);
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    fireEvent.change(await screen.findByRole("textbox", { name: "Chat input" }), {
      target: { value: "What is 2 + 2?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("The answer is 4.");
    expect(screen.getAllByText("calculator.evaluate").length).toBeGreaterThan(0);
    expect(screen.queryByText(/enabled_tools/)).toBeNull();
  });

  it("presents a failed request returned by the M1 endpoint", async () => {
    const fetchMock = vi.fn(async (path: string, _init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions") return jsonResponse({ session_id: "chat-1" }, 201);
      if (path === "/api/sessions/chat-1/messages/stream") {
        return jsonResponse({ detail: "Model unavailable" }, 502);
      }
      if (path === "/api/sessions/chat-1/timeline") return jsonResponse([]);
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    fireEvent.change(await screen.findByRole("textbox", { name: "Chat input" }), {
      target: { value: "Hello" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText(/Model unavailable/);
  });

  it("sends the canonical cancellation request after receiving the SSE request identifier", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/models") return Promise.resolve(jsonResponse([]));
      if (path === "/api/sessions")
        return Promise.resolve(jsonResponse({ session_id: "chat-1" }, 201));
      if (path === "/api/sessions/chat-1/messages/stream") {
        const body = new ReadableStream({
          start(controller) {
            controller.enqueue(
              new TextEncoder().encode(
                "data: " +
                  JSON.stringify({
                    type: "request.accepted",
                    created_at: "now",
                    payload: { request_id: "req-1", session_id: "chat-1" },
                  }) +
                  "\n\n",
              ),
            );
            setTimeout(() => controller.close(), 100);
          },
        });
        return Promise.resolve(
          new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
        );
      }
      if (path === "/api/requests/req-1/cancel")
        return Promise.resolve(jsonResponse({ status: "cancellation_requested" }));
      if (path === "/api/sessions/chat-1/timeline") return Promise.resolve(jsonResponse([]));
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    fireEvent.change(await screen.findByRole("textbox", { name: "Chat input" }), {
      target: { value: "Cancel me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    const stopButton = await screen.findByRole("button", { name: "Stop generating" });
    fireEvent.click(stopButton);

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([path]) => path === "/api/requests/req-1/cancel")).toBe(
        true,
      ),
    );
    await screen.findByText(/Yêu cầu đã được hủy/);
  });

  it("uploads into the active Chat session and presents its ready lifecycle state", async () => {
    const document = {
      document_id: "doc-1",
      source: { kind: "session", source_id: "chat-1" },
      name: "runbook.md",
      media_type: "text/markdown",
    };
    const fetchMock = vi.fn(async (path: string, _init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions") return jsonResponse({ session_id: "chat-1" }, 201);
      if (path === "/api/sessions/chat-1/attachments") {
        return jsonResponse(
          { document, attachment_id: "attachment-1", status: "ready", error_message: null },
          201,
        );
      }
      if (path === "/api/sessions/chat-1/timeline") {
        return jsonResponse([
          {
            item_id: "attachment-1",
            session_id: "chat-1",
            created_at: "2026-08-25T00:00:00Z",
            kind: "attachment",
            payload: { document, attachment_id: "attachment-1", status: "ready" },
            call_id: null,
            tool_name: null,
          },
        ]);
      }
      if (path === "/api/sessions/chat-1/documents/doc-1") {
        return jsonResponse({
          document,
          attachment_id: "attachment-1",
          status: "ready",
          error_message: null,
          deleted: false,
          ingestion: [
            { state: "uploaded", error_message: null, created_at: "now" },
            { state: "parsing", error_message: null, created_at: "now" },
            { state: "indexing", error_message: null, created_at: "now" },
            { state: "ready", error_message: null, created_at: "now" },
          ],
        });
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["# Runbook"], "runbook.md", { type: "text/markdown" });
    Object.assign(file, { text: async () => "# Runbook" });

    renderChat();
    const attachmentInput = (await screen.findAllByLabelText("Attach document")).find(
      (element) => element.tagName === "INPUT",
    );
    fireEvent.change(attachmentInput!, {
      target: { files: [file] },
    });

    await screen.findAllByText("runbook.md");
    expect(screen.getByText("Sẵn sàng")).not.toBeNull();
    expect(fetchMock.mock.calls.map(([path]) => path)).toContain(
      "/api/sessions/chat-1/attachments",
    );
    const request = fetchMock.mock.calls.find(
      ([path]) => path === "/api/sessions/chat-1/attachments",
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      name: "runbook.md",
      content: "# Runbook",
      media_type: "text/markdown",
    });
  });

  it("reconnects a failed ingestion state separately from model and tool failures", async () => {
    window.localStorage.setItem("orion-m1-session-ids", JSON.stringify(["chat-1"]));
    const document = {
      document_id: "doc-failed",
      source: { kind: "session", source_id: "chat-1" },
      name: "scan.pdf",
      media_type: "application/pdf",
    };
    const fetchMock = vi.fn(async (path: string) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions/chat-1/timeline") {
        return jsonResponse([
          {
            item_id: "attachment-failed",
            session_id: "chat-1",
            created_at: "2026-08-25T00:00:00Z",
            kind: "attachment",
            payload: { document, attachment_id: "attachment-failed", status: "failed" },
            call_id: null,
            tool_name: null,
          },
        ]);
      }
      if (path === "/api/sessions/chat-1/documents/doc-failed") {
        return jsonResponse({
          document,
          attachment_id: "attachment-failed",
          status: "failed",
          error_message: "Unsupported document format",
          deleted: false,
          ingestion: [
            { state: "uploaded", error_message: null, created_at: "now" },
            { state: "parsing", error_message: null, created_at: "now" },
            { state: "failed", error_message: "Unsupported document format", created_at: "now" },
          ],
        });
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    await screen.findAllByText("scan.pdf");
    expect(screen.getByText("Không thể nhập")).not.toBeNull();
    expect(screen.getByText("Unsupported document format")).not.toBeNull();
  });

  it("reconstructs grounded citations from canonical sources and opens exact page/section metadata", async () => {
    window.localStorage.setItem("orion-m1-session-ids", JSON.stringify(["chat-1"]));
    const document = {
      document_id: "doc-1",
      source: { kind: "session", source_id: "chat-1" },
      name: "security.md",
      media_type: "text/markdown",
    };
    const timeline = [
      {
        item_id: "attachment-1",
        session_id: "chat-1",
        created_at: "2026-08-25T00:00:00Z",
        kind: "attachment",
        payload: { document, attachment_id: "attachment-1", status: "ready" },
        call_id: null,
        tool_name: null,
      },
      {
        item_id: "search-1",
        session_id: "chat-1",
        created_at: "2026-08-25T00:00:01Z",
        kind: "tool_result",
        payload: {
          result: {
            status: "success",
            sources: [
              {
                source_ref_id: "source-1",
                source_kind: "session",
                source_id: "chat-1",
                document_id: "doc-1",
                segment_id: "segment-1",
                page: 7,
                section: "Security",
                label: "security.md",
              },
            ],
          },
        },
        call_id: "search-1",
        tool_name: "knowledge.search",
      },
      {
        item_id: "answer-1",
        session_id: "chat-1",
        created_at: "2026-08-25T00:00:02Z",
        kind: "assistant_message",
        payload: {
          content: "The policy requires review. [[source:source-1]] [[source:invented-source]]",
          citation_source_ref_ids: ["source-1", "invented-source"],
        },
        call_id: null,
        tool_name: null,
      },
    ];
    const fetchMock = vi.fn(async (path: string) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions/chat-1/timeline") return jsonResponse(timeline);
      if (path === "/api/sessions/chat-1/documents/doc-1") {
        return jsonResponse({
          document,
          attachment_id: "attachment-1",
          status: "ready",
          error_message: null,
          deleted: false,
          ingestion: [],
        });
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    const source = (await screen.findAllByRole("button", { name: "Open source security.md" }))[0];
    expect(screen.queryByText(/invented-source/)).toBeNull();
    fireEvent.click(source);

    await screen.findByText("Trang 7 · Security");
    expect(screen.getByText("knowledge.search")).not.toBeNull();
  });

  it("removes tombstoned documents and their source cards after deletion", async () => {
    window.localStorage.setItem("orion-m1-session-ids", JSON.stringify(["chat-1"]));
    const document = {
      document_id: "doc-1",
      source: { kind: "session", source_id: "chat-1" },
      name: "obsolete.txt",
      media_type: "text/plain",
    };
    const timeline = [
      {
        item_id: "attachment-1",
        session_id: "chat-1",
        created_at: "2026-08-25T00:00:00Z",
        kind: "attachment",
        payload: { document, attachment_id: "attachment-1", status: "ready" },
        call_id: null,
        tool_name: null,
      },
    ];
    let statusCalls = 0;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([]);
      if (path === "/api/sessions/chat-1/timeline") return jsonResponse(timeline);
      if (path === "/api/sessions/chat-1/documents/doc-1" && init?.method === "DELETE") {
        return jsonResponse({ status: "deleted" });
      }
      if (path === "/api/sessions/chat-1/documents/doc-1") {
        statusCalls += 1;
        if (statusCalls > 1) return jsonResponse({ detail: "Document not found." }, 404);
        return jsonResponse({
          document,
          attachment_id: "attachment-1",
          status: "ready",
          error_message: null,
          deleted: false,
          ingestion: [],
        });
      }
      throw new Error("unexpected endpoint " + path);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChat();
    await screen.findAllByText("obsolete.txt");
    fireEvent.click(screen.getByRole("button", { name: "Delete obsolete.txt" }));

    await waitFor(() => expect(screen.queryAllByText("obsolete.txt")).toHaveLength(0));
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) =>
          path === "/api/sessions/chat-1/documents/doc-1" && init?.method === "DELETE",
      ),
    ).toBe(true);
  });
});
