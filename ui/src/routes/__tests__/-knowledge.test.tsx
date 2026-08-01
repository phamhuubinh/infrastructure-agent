import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setStoredApiKey } from "@/lib/api";
import { KnowledgePage } from "@/routes/knowledge";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("project-scoped RAG page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("loads project-scoped documents and analyses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        projects: [
          {
            id: "project-alpha",
            name: "Project Alpha",
            description: "Alpha corpus",
            documents: [
              {
                id: "doc-alpha",
                filename: "alpha.md",
                content_type: "text/markdown",
                size_bytes: 128,
                chunk_count: 2,
                created_at: "2026-08-02T00:00:00Z",
              },
            ],
            analyses: [],
            created_at: "2026-08-02T00:00:00Z",
            updated_at: "2026-08-02T00:00:00Z",
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgePage />);

    expect((await screen.findAllByText("Project Alpha")).length).toBeGreaterThan(0);
    expect(screen.getByText("alpha.md")).toBeTruthy();
    expect(screen.getByText("128 B · 2 chunks")).toBeTruthy();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("sends the configured API key through the RAG proxy request", async () => {
    setStoredApiKey("browser-secret");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ projects: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgePage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestInit.headers).get("X-API-Key")).toBe("browser-secret");
  });
});
