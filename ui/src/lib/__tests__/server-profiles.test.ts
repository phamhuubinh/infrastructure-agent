import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  vi.resetModules();
});

describe("server profile isolation", () => {
  it("aborts legacy JSON body consumption when switching even to the same origin", async () => {
    const profiles = await import("../server-profiles");
    const cancel = vi.fn();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("["));
          },
          cancel,
        }),
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    const response = await profiles.serverResponse("list_sessions_api_sessions_get", {});
    const parsed = response.json();
    const rejected = expect(parsed).rejects.toThrow();
    profiles.activateServer({
      id: "same",
      name: "Same origin, new context",
      origin: window.location.origin,
    });
    await rejected;
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not expire the new server after an old native refresh is interrupted", async () => {
    const profiles = await import("../server-profiles");
    const pair = {
      session_id: "a".repeat(32),
      token_type: "Bearer" as const,
      access_token: "orion_access_" + "a".repeat(43),
      refresh_token: "orion_refresh_" + "b".repeat(43),
      access_expires_at: 2000000000,
      refresh_expires_at: 2001000000,
    };
    let finish!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>(async (url) =>
      String(url).endsWith("/refresh")
        ? new Promise<Response>((resolve) => {
            finish = resolve;
          })
        : new Response("", { status: 401, headers: { "X-Orion-Auth-Expired": "1" } }),
    );
    profiles.installNativeHost({
      platform: "windows",
      fetch: fetcher,
      tokens: { get: async () => pair, set: vi.fn(), clear: vi.fn() },
    });
    profiles.activateServer({ id: "a", name: "A", origin: "https://a.example" });
    const api = await import("../api");
    const expired = vi.fn();
    window.addEventListener(api.AUTH_EXPIRED_EVENT, expired);
    try {
      const request = api.apiFetch("/api/models");
      const rejected = expect(request).rejects.toThrow("cancelled");
      await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
      profiles.activateServer({ id: "b", name: "B", origin: "https://b.example" });
      finish(
        new Response(JSON.stringify({ ...pair, access_token: "orion_access_" + "c".repeat(43) })),
      );
      await rejected;
      expect(expired).not.toHaveBeenCalled();
      expect(profiles.activeServer().origin).toBe("https://b.example");
    } finally {
      window.removeEventListener(api.AUTH_EXPIRED_EVENT, expired);
    }
  });
  it("persists public profile metadata only, validates origins and does not auto-connect", async () => {
    const profiles = await import("../server-profiles");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const profile = profiles.saveServerProfile("Server A", "https://a.example");
    expect(profiles.serverProfiles()).toEqual([profile]);
    expect(profiles.activeServer().origin).toBe(window.location.origin);
    expect(fetcher).not.toHaveBeenCalled();
    for (const origin of [
      "https://user:password@a.example",
      "http://remote.example",
      "https://a.example/path",
      "https://a.example?secret=token",
    ]) {
      expect(() => profiles.saveServerProfile("Unsafe", origin)).toThrow("configuration");
    }
    const serialized = localStorage.getItem("orion-server-profiles-v1")!;
    expect(Object.keys(JSON.parse(serialized)[0]).sort()).toEqual(["id", "name", "origin"]);
    expect(() => profiles.saveServerProfile("Duplicate", "https://a.example")).toThrow(
      "configuration",
    );
  });

  it("rejects stale native responses on server switch even if the bridge ignores abort", async () => {
    const profiles = await import("../server-profiles");
    let resolve!: (value: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    profiles.installNativeHost({
      platform: "windows",
      fetch: fetcher,
      tokens: {
        get: async () => ({
          session_id: "a".repeat(32),
          token_type: "Bearer",
          access_token: "orion_access_" + "a".repeat(43),
          refresh_token: "orion_refresh_" + "b".repeat(43),
          access_expires_at: 2000000000,
          refresh_expires_at: 2001000000,
        }),
        set: vi.fn(),
        clear: vi.fn(),
      },
    });
    profiles.activateServer({ id: "a", name: "A", origin: "https://a.example" });
    const response = profiles.serverRequest("list_sessions_api_sessions_get", {});
    const rejected = expect(response).rejects.toThrow(/cancelled|authentication/);
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    profiles.activateServer({ id: "b", name: "B", origin: "https://b.example" });
    resolve(new Response("[]"));
    await rejected;
    expect(fetcher.mock.calls[0][0]).toBe("https://a.example/api/sessions");
    expect(profiles.activeServer().origin).toBe("https://b.example");
  });
});
