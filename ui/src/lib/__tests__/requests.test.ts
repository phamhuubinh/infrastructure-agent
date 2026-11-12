import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelIntent,
  pendingIntent,
  pendingObservation,
  requestIntent,
  runIntent,
} from "../requests";
import { activateServer } from "../server-profiles";

afterEach(() => vi.unstubAllGlobals());
const acceptedId = "302f721b-1497-49a8-ac76-68c9476dfb08";
const completedId = "148a345d-beda-4938-a387-008c326a909c";
const record = (event_id: string, type: string) => ({
  event_id,
  type,
  created_at: "2026-10-31T00:00:00Z",
  payload: {},
});
const json = (value: unknown) =>
  new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
function stream(events: ReturnType<typeof record>[]) {
  return new Response(
    events.map((event) => `id: ${event.event_id}\ndata: ${JSON.stringify(event)}\n\n`).join(""),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("durable shared chat transport", () => {
  it("never sends an old nonce from cleanup after a server context switch", async () => {
    const intent = requestIntent("old-context", "Private old intent");
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    activateServer({ id: "same-origin", name: "New context", origin: window.location.origin });
    await expect(cancelIntent(intent)).rejects.toThrow("Server đã thay đổi");
    expect(fetcher).not.toHaveBeenCalled();
    expect(pendingIntent("old-context")).toBeNull();
  });
  it("retains an ambiguous admission nonce for explicit recovery instead of creating another intent", async () => {
    const intent = requestIntent("unknown-session", "One uncertain mutation");
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("lost"))
      .mockRejectedValueOnce(new Error("lost again"))
      .mockResolvedValueOnce(json({ request_id: "existing", status: "running" }))
      .mockResolvedValueOnce(stream([record(completedId, "request.completed")]));
    vi.stubGlobal("fetch", fetcher);
    await expect(
      runIntent(
        intent,
        () => {},
        () => {},
        new AbortController().signal,
      ),
    ).rejects.toThrow("network");
    expect(pendingIntent("unknown-session")).toBe(intent);
    expect(pendingObservation("unknown-session")).toBeNull();
    expect(requestIntent("unknown-session", intent.content)).toBe(intent);
    expect(() => requestIntent("unknown-session", "Changed intent")).toThrow("chưa xác minh");
    await runIntent(
      intent,
      () => {},
      () => {},
      new AbortController().signal,
    );
    expect(fetcher.mock.calls[0][1]?.body).toBe(fetcher.mock.calls[2][1]?.body);
    expect(pendingIntent("unknown-session")).toBeNull();
  });

  it("retries known request observation without returning to admission", async () => {
    const intent = requestIntent("known-session", "Known request");
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ request_id: "known", status: "running" }))
      .mockResolvedValueOnce(new Response("unavailable", { status: 503 }))
      .mockRejectedValueOnce(new Error("page unavailable"))
      .mockResolvedValueOnce(stream([record(completedId, "request.completed")]));
    vi.stubGlobal("fetch", fetcher);
    await expect(
      runIntent(
        intent,
        () => {},
        () => {},
        new AbortController().signal,
      ),
    ).rejects.toThrow("network");
    expect(pendingObservation("known-session")).toBe(intent);
    await runIntent(
      intent,
      () => {},
      () => {},
      new AbortController().signal,
    );
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(fetcher.mock.calls[3][0]).toBe("/api/requests/known/stream");
  });

  it("does not confirm Stop until the canonical request status becomes terminal", async () => {
    const intent = requestIntent("stopping-session", "Stop after admission");
    let finish!: (response: Response) => void;
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ request_id: "stopping", status: "running" }))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      );
    vi.stubGlobal("fetch", fetcher);
    let completed = false;
    const cancellation = cancelIntent(intent).then(() => {
      completed = true;
    });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(completed).toBe(false);
    finish(json({ request_id: "stopping", status: "cancelled" }));
    await cancellation;
    expect(pendingIntent("stopping-session")).toBeNull();
  });
  it("resumes GET observation after EOF without another admission", async () => {
    let streams = 0;
    const fetcher = vi.fn<typeof fetch>(async (url, init) => {
      const path = String(url);
      if (init?.method === "POST") return json({ request_id: "request", status: "running" });
      if (path.includes("event-page")) {
        expect(path).toContain(acceptedId);
        return json({ events: [], has_more: false, next_cursor: acceptedId, status: "running" });
      }
      streams++;
      if (streams === 1) return stream([record(acceptedId, "request.accepted")]);
      expect(path).toContain(acceptedId);
      return stream([record(completedId, "request.completed")]);
    });
    vi.stubGlobal("fetch", fetcher);
    const admitted = vi.fn();
    const events: string[] = [];
    await runIntent(
      requestIntent("session", "Run once"),
      admitted,
      (event) => {
        events.push(event.event_id);
      },
      new AbortController().signal,
    );
    expect(admitted).toHaveBeenCalledExactlyOnceWith("request");
    expect(events).toEqual([acceptedId, completedId]);
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("keeps the same nonce/content after a lost admission reply and uses it for Stop", async () => {
    const intent = requestIntent("session", "One mutation intent");
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("lost acknowledgement"))
      .mockResolvedValueOnce(json({ request_id: "same-request", status: "running" }))
      .mockResolvedValueOnce(stream([record(completedId, "request.completed")]))
      .mockResolvedValueOnce(json({ request_id: "same-request", status: "completed" }));
    vi.stubGlobal("fetch", fetcher);
    await runIntent(
      intent,
      () => {},
      () => {},
      new AbortController().signal,
    );
    await cancelIntent(intent);
    expect(fetcher.mock.calls[0][1]?.body).toBe(fetcher.mock.calls[1][1]?.body);
    expect(fetcher.mock.calls[3][1]?.body).toBe(fetcher.mock.calls[0][1]?.body);
    expect(fetcher.mock.calls[3][0]).toBe("/api/sessions/session/request-cancellations");
  });

  it("recovers a missing terminal stream event from the durable page", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ request_id: "request", status: "running" }))
      .mockResolvedValueOnce(stream([record(acceptedId, "request.accepted")]))
      .mockResolvedValueOnce(
        json({
          events: [record(completedId, "request.cancelled")],
          next_cursor: completedId,
          has_more: false,
          status: "cancelled",
        }),
      );
    vi.stubGlobal("fetch", fetcher);
    const events: string[] = [];
    await runIntent(
      requestIntent("session", "work"),
      () => {},
      (event) => {
        events.push(event.type);
      },
      new AbortController().signal,
    );
    expect(events).toEqual(["request.accepted", "request.cancelled"]);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});
