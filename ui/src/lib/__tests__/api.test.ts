import { describe, expect, it, vi } from "vitest";

import {
  apiErrorMessage,
  apiFetch,
  attachSessionDocument,
  deleteSessionDocument,
  sessionDocumentStatus,
} from "@/lib/api";

describe("M1 API client", () => {
  it("does not retain or attach browser credentials", async () => {
    const originalFetch = globalThis.fetch;
    let captured: Headers | undefined;
    globalThis.fetch = async (_input, init) => {
      captured = new Headers(init?.headers);
      return new Response("{}", { status: 200 });
    };

    try {
      await apiFetch("/api/models");
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(captured?.has("Authorization")).toBe(false);
    expect(captured?.has("X-API-Key")).toBe(false);
  });

  it("keeps a canonical API detail message", async () => {
    const response = new Response('{"detail":"No active model configuration"}', {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
    await expect(apiErrorMessage(response)).resolves.toBe("No active model configuration");
  });

  it("uses only the M2 session-scoped attachment, status, and tombstone routes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            document: {
              document_id: "doc-1",
              source: { kind: "session", source_id: "session-1" },
              name: "notes.txt",
              media_type: "text/plain",
            },
            attachment_id: "attachment-1",
            status: "uploaded",
            error_message: null,
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(new Response('{"detail":"Document not found."}', { status: 404 }))
      .mockResolvedValueOnce(new Response('{"status":"deleted"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await attachSessionDocument("session-1", {
      name: "notes.txt",
      content: "local text",
      media_type: "text/plain",
    });
    await expect(sessionDocumentStatus("session-1", "doc-1")).resolves.toBeNull();
    await deleteSessionDocument("session-1", "doc-1");

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/sessions/session-1/attachments",
      "/api/sessions/session-1/documents/doc-1",
      "/api/sessions/session-1/documents/doc-1",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      name: "notes.txt",
      content: "local text",
      media_type: "text/plain",
    });
    expect(fetchMock.mock.calls[2][1]?.method).toBe("DELETE");
  });
});
