import { describe, expect, it } from "vitest";

import { apiErrorMessage, apiFetch } from "@/lib/api";

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
});
