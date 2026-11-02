// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { OrionClient, type SecureTokenStore, type TokenPair } from "./client";
import { serverEvents } from "./events";

const origin = "https://orion.example";
const pair = (letter = "a"): TokenPair => ({
  session_id: "a".repeat(32),
  token_type: "Bearer",
  access_token: "orion_access_" + letter.repeat(43),
  refresh_token: "orion_refresh_" + letter.repeat(43),
  access_expires_at: 2000000000,
  refresh_expires_at: 2001000000,
});
function vault(initial: TokenPair | null = pair()) {
  const records = new Map<string, TokenPair>();
  if (initial) records.set(origin, initial);
  const store: SecureTokenStore = {
    get: vi.fn(async (key) => records.get(key) ?? null),
    set: vi.fn(async (key, value) => {
      records.set(key, value);
    }),
    clear: vi.fn(async (key) => {
      records.delete(key);
    }),
  };
  return { store, records };
}
const json = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
const expired = () =>
  new Response("credential must never be echoed", {
    status: 401,
    headers: { "X-Orion-Auth-Expired": "1" },
  });

describe("shared client authentication and replay boundaries", () => {
  it("accepts HTTPS and literal loopback only, rejects injected server authorities", () => {
    for (const value of [
      "http://remote.test",
      "https://u:p@orion.example",
      origin + "/nested",
      origin + "?token=secret",
      "file:///x",
    ]) {
      expect(() => new OrionClient({ origin: value, mode: "browser" })).toThrow("configuration");
    }
    expect(new OrionClient({ origin: "http://127.0.0.1:8000", mode: "browser" }).origin).toBe(
      "http://127.0.0.1:8000",
    );
  });

  it("uses server-scoped vault credentials, omits native cookies and forbids redirect following", async () => {
    const { store } = vault();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json([]));
    const client = new OrionClient({ origin, mode: "native", fetch: fetcher, tokens: store });
    await client.request("list_sessions_api_sessions_get", {});
    expect(store.get).toHaveBeenCalledWith(origin);
    const init = fetcher.mock.calls[0][1]!;
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer " + pair().access_token);
    expect(init.credentials).toBe("omit");
    expect(init.redirect).toBe("error");
    const other = new OrionClient({
      origin: "https://other.example",
      mode: "native",
      fetch: fetcher,
      tokens: store,
    });
    await expect(other.request("list_sessions_api_sessions_get", {})).rejects.toThrow(
      "authentication",
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("refreshes concurrent refusals once and rotates the vault before retry", async () => {
    const { store, records } = vault();
    let rotations = 0;
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith("/refresh")) {
        rotations++;
        await Promise.resolve();
        return json(pair("b"));
      }
      return new Headers(init?.headers).get("Authorization") === "Bearer " + pair().access_token
        ? expired()
        : json([]);
    });
    const client = new OrionClient({ origin, mode: "native", fetch: fetcher, tokens: store });
    await Promise.all([
      client.request("list_sessions_api_sessions_get", {}),
      client.request("list_sessions_api_sessions_get", {}),
    ]);
    expect(rotations).toBe(1);
    expect(records.get(origin)).toEqual(pair("b"));
    expect(fetcher).toHaveBeenCalledTimes(5);
  });

  it("does not refresh an ordinary 401 or expose its body", async () => {
    const { store } = vault();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("secret-token", { status: 401 }));
    const client = new OrionClient({ origin, mode: "native", fetch: fetcher, tokens: store });
    await expect(client.request("list_sessions_api_sessions_get", {})).rejects.toThrow(
      /^Orion client authentication error$/,
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("clears an ambiguous refresh outcome and never resends the old refresh token", async () => {
    const { store, records } = vault();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(expired())
      .mockRejectedValueOnce(new Error("secret internal URL"));
    const client = new OrionClient({ origin, mode: "native", fetch: fetcher, tokens: store });
    await expect(client.request("list_sessions_api_sessions_get", {})).rejects.toThrow(
      /^Orion client authentication error$/,
    );
    await expect(client.request("list_sessions_api_sessions_get", {})).rejects.toThrow(
      "authentication",
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(records.has(origin)).toBe(false);
  });

  it("retries admission with an immutable UUID and body after a lost response", async () => {
    const input = {
      path: { session_id: "session" },
      body: { content: "one intent", client_request_id: "a2550eca-41bb-4242-9f2b-4cd4bd1aa49e" },
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(async () => {
        input.body.content = "later edit";
        throw new Error("lost response");
      })
      .mockResolvedValueOnce(json({ request_id: "same durable request" }));
    const client = new OrionClient({ origin, mode: "browser", fetch: fetcher });
    await client.request("admit_api_sessions__session_id__requests_post", input);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][1]?.body).toBe(fetcher.mock.calls[1][1]?.body);
    expect(String(fetcher.mock.calls[1][1]?.body)).toContain("one intent");
  });

  it("never retries a command mutation after an ambiguous network outcome", async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new Error("unknown"));
    const client = new OrionClient({ origin, mode: "browser", fetch: fetcher });
    await expect(
      client.request("manual_operation_api_endpoints__endpoint_id__operation_post", {
        path: { endpoint_id: "device" },
        body: { operation: "file.write", arguments: {} },
      }),
    ).rejects.toThrow("network");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("returns binary streams without JSON parsing and sends binary uploads unchanged", async () => {
    const bytes = new Uint8Array([0, 255, 10]);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(bytes))
      .mockResolvedValueOnce(json({ written: true }));
    const client = new OrionClient({ origin, mode: "browser", fetch: fetcher });
    const stream = await client.request("download_api_endpoints__endpoint_id__download_post", {
      path: { endpoint_id: "device" },
      body: { path: "/data" },
    });
    expect(await new Response(stream).arrayBuffer()).toEqual(bytes.buffer);
    const blob = new Blob([bytes]);
    await client.request("upload_api_endpoints__endpoint_id__upload_post", {
      path: { endpoint_id: "device" },
      headers: { "x-endpoint-path": "/data" },
      body: blob,
    });
    expect(fetcher.mock.calls[1][1]?.body).toBe(blob);
  });

  it("cancels without replay and does not dispatch a pre-aborted request", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const controller = new AbortController();
    controller.abort();
    const client = new OrionClient({ origin, mode: "browser", fetch: fetcher });
    await expect(
      client.request("list_sessions_api_sessions_get", {}, controller.signal),
    ).rejects.toThrow("cancelled");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not restore tokens when logout races an in-flight refresh", async () => {
    const { store, records } = vault();
    let finish!: (response: Response) => void;
    let entered!: () => void;
    const waiting = new Promise<void>((resolve) => {
      entered = resolve;
    });
    const fetcher = vi.fn<typeof fetch>(async (url) => {
      if (String(url).endsWith("/refresh")) {
        entered();
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      }
      if (String(url).endsWith("/logout")) return json({ revoked: true });
      return expired();
    });
    const client = new OrionClient({ origin, mode: "native", fetch: fetcher, tokens: store });
    const request = client.request("list_sessions_api_sessions_get", {});
    const rejected = expect(request).rejects.toThrow("authentication");
    await waiting;
    await client.logout();
    finish(json(pair("b")));
    await rejected;
    expect(records.has(origin)).toBe(false);
  });
});

describe("incremental observation decoding", () => {
  it("handles Unicode split at every byte, CRLF, comments, multiple data lines and incomplete EOF", async () => {
    const bytes = new TextEncoder().encode(
      ": heartbeat\r\nid: event-uuid\r\ndata: Tiếng Việt\r\ndata: second\r\n\r\ndata: unfinished",
    );
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    });
    const result = [];
    for await (const event of serverEvents(stream)) result.push(event);
    expect(result).toEqual([{ id: "event-uuid", event: "message", data: "Tiếng Việt\nsecond" }]);
  });

  it("cancels the underlying observation on consumer disconnect", async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data: first\n\n"));
      },
      cancel,
    });
    for await (const event of serverEvents(stream)) {
      expect(event.data).toBe("first");
      break;
    }
    expect(cancel).toHaveBeenCalledTimes(1);
  });
});
