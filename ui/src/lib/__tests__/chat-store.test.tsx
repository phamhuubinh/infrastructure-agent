import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatProvider, useChat } from "@/lib/chat-store";

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
    screen.getByRole("button", { name: "create" }).click();

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
    screen.getByRole("button", { name: "load" }).click();

    await screen.findByText("Hello|Hi");
    expect(fetchMock).toHaveBeenCalledWith("/api/sessions/session-1/timeline", expect.anything());
  });
});
