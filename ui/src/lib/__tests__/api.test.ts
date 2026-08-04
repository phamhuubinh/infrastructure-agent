import { afterEach, describe, expect, it } from "vitest";

import { apiErrorMessage, apiFetch, setStoredApiKey } from "@/lib/api";

afterEach(() => {
  setStoredApiKey("");
});

describe("apiFetch", () => {
  it("sends the browser API key when direct backend access needs it", async () => {
    setStoredApiKey("browser-secret");
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

    expect(captured?.get("X-API-Key")).toBe("browser-secret");
  });
});

describe("apiErrorMessage", () => {
  it("turns an authentication JSON response into an actionable message", async () => {
    const response = new Response('{"detail":"Invalid or missing API key"}', {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

    await expect(apiErrorMessage(response)).resolves.toContain("reverse proxy");
  });

  it("keeps a normal API detail message", async () => {
    const response = new Response('{"detail":"Model connection failed"}', {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });

    await expect(apiErrorMessage(response)).resolves.toBe("Model connection failed");
  });
});
