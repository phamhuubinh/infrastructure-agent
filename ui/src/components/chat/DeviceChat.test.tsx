import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { DeviceChat } from "./DeviceChat";

const mocks = vi.hoisted(() => ({ json: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiJson: mocks.json, apiFetch: mocks.fetch }));
vi.mock("./AssistantMarkdown", () => ({
  AssistantMarkdown: ({ children }: { children: string }) => <p>{children}</p>,
}));
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

it("loads only the endpoint-owned session/history and persists its independent mutation mode", async () => {
  mocks.json.mockImplementation((url: string, options?: RequestInit) => {
    if (url.endsWith("/chat"))
      return Promise.resolve({
        session_id: "device-session",
        endpoint_id: "a".repeat(32),
        mutation_mode: "read_only",
      });
    if (url.endsWith("/timeline"))
      return Promise.resolve([
        { item_id: "1", kind: "user_message", payload: { content: "Device-only history" } },
      ]);
    if (options?.method === "PATCH") return Promise.resolve({ mutation_mode: "confirm" });
    return Promise.resolve([]);
  });
  render(<DeviceChat endpointId={"a".repeat(32)} />);
  expect(await screen.findByText("Device-only history")).toBeTruthy();
  expect(screen.queryByLabelText("Attach document")).toBeNull();
  fireEvent.change(screen.getByLabelText("Quyền sửa Device Chat"), {
    target: { value: "confirm" },
  });
  await waitFor(() =>
    expect((screen.getByLabelText("Quyền sửa Device Chat") as HTMLSelectElement).value).toBe(
      "confirm",
    ),
  );
  expect(mocks.json).toHaveBeenCalledWith(
    "/api/sessions/device-session/mutation-mode",
    expect.objectContaining({
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
    }),
  );
  expect(
    mocks.json.mock.calls.some(([url]) => url === "/api/sessions" || url.includes("/projects")),
  ).toBe(false);
});

it("submits Device Chat with the JSON media type required by the API", async () => {
  mocks.json.mockImplementation((url: string) =>
    Promise.resolve(
      url.endsWith("/chat")
        ? { session_id: "device-session", endpoint_id: "a".repeat(32), mutation_mode: "read_only" }
        : [],
    ),
  );
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/requests"))
      return new Response(JSON.stringify({ request_id: "device-request", status: "running" }));
    if (url.endsWith("/stream")) {
      const event = {
        event_id: "907dbefb-510b-4df8-82eb-384d248bdf88",
        type: "request.completed",
        created_at: "2026-10-31T00:00:00Z",
        payload: {},
      };
      return new Response(`id: ${event.event_id}\ndata: ${JSON.stringify(event)}\n\n`);
    }
    return new Response("{}");
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DeviceChat endpointId={"a".repeat(32)} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Gửi Device Chat" })).toBeTruthy());
  fireEvent.change(screen.getByLabelText("Nhắn Device Chat"), {
    target: { value: "Inspect device" },
  });
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "Gửi Device Chat" }) as HTMLButtonElement).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "Gửi Device Chat" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  const [url, init] = fetcher.mock.calls[0];
  const request = new Request("https://orion.test" + url, init);
  expect(request.headers.get("content-type")).toBe("application/json");
  expect(await request.json()).toEqual({
    content: "Inspect device",
    client_request_id: expect.any(String),
  });
  expect(url).toBe("/api/sessions/device-session/requests");
  expect(fetcher.mock.calls[1][0]).toBe("/api/requests/device-request/stream");
});
