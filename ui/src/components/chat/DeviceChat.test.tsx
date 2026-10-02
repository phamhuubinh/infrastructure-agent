import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { DeviceChat } from "./DeviceChat";

const mocks = vi.hoisted(() => ({ json: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiJson: mocks.json, apiFetch: mocks.fetch }));
vi.mock("@/lib/chat-stream", () => ({ parseSseEvents: () => ({ events: [], remainder: "" }) }));
vi.mock("./AssistantMarkdown", () => ({
  AssistantMarkdown: ({ children }: { children: string }) => <p>{children}</p>,
}));
afterEach(() => vi.clearAllMocks());

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
    expect.objectContaining({ method: "PATCH" }),
  );
  expect(
    mocks.json.mock.calls.some(([url]) => url === "/api/sessions" || url.includes("/projects")),
  ).toBe(false);
});
