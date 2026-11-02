import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { CommandApprovalReview } from "./CommandApprovalReview";

const mocks = vi.hoisted(() => ({ payload: vi.fn(), resolve: vi.fn() }));
vi.mock("@/lib/api", () => ({
  getToolAuthorizationPayload: mocks.payload,
  resolveToolAuthorization: mocks.resolve,
}));

afterEach(() => vi.clearAllMocks());

const props = {
  sessionId: "session-a",
  requestId: "request-a",
  callId: "call-a",
  toolName: "system.command.run",
  onResolved: vi.fn(),
};
const payload = {
  tool_name: "system.command.run",
  payload_hash: "a".repeat(64),
  arguments: {
    target_ref: "worker-a",
    shell: "powershell",
    command: "Write-Output '<exact & command>'",
    timeout_seconds: 60,
    max_output_bytes: 1024,
  },
};

it("shows the exact escaped script before allowing and binds approval to the reviewed hash", async () => {
  let complete: (value: typeof payload) => void = () => {};
  mocks.payload.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve;
    }),
  );
  mocks.resolve.mockResolvedValue(undefined);
  render(<CommandApprovalReview {...props} />);
  expect(
    (screen.getByRole("button", { name: "Cho phép lệnh này" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  complete(payload);
  expect(await screen.findByLabelText("Lệnh chờ xác nhận")).toHaveProperty(
    "textContent",
    payload.arguments.command,
  );
  fireEvent.click(screen.getByRole("button", { name: "Cho phép lệnh này" }));
  await waitFor(() =>
    expect(mocks.resolve).toHaveBeenCalledWith(
      "session-a",
      "request-a",
      "call-a",
      "allow",
      payload.payload_hash,
    ),
  );
  expect(props.onResolved).toHaveBeenCalled();
});

it("allows denial when payload loading fails while keeping execution disabled", async () => {
  mocks.payload.mockRejectedValue(new Error("unavailable"));
  mocks.resolve.mockResolvedValue(undefined);
  render(<CommandApprovalReview {...props} />);
  await screen.findByRole("alert");
  expect(
    (screen.getByRole("button", { name: "Cho phép lệnh này" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Từ chối" }));
  await waitFor(() =>
    expect(mocks.resolve).toHaveBeenCalledWith(
      "session-a",
      "request-a",
      "call-a",
      "deny",
      undefined,
    ),
  );
});

it("rejects payloads for a different operation", async () => {
  mocks.payload.mockResolvedValue({ ...payload, tool_name: "system.command.cancel" });
  render(<CommandApprovalReview {...props} />);
  await screen.findByRole("alert");
  expect(
    (screen.getByRole("button", { name: "Cho phép lệnh này" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  expect(screen.queryByLabelText("Lệnh chờ xác nhận")).toBeNull();
});

it("keeps approval disabled when the exact script is missing", async () => {
  mocks.payload.mockResolvedValue({
    ...payload,
    arguments: { target_ref: "worker-a", shell: "powershell" },
  });
  render(<CommandApprovalReview {...props} />);
  await screen.findByRole("alert");
  expect(
    (screen.getByRole("button", { name: "Cho phép lệnh này" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  expect(screen.queryByLabelText("Lệnh chờ xác nhận")).toBeNull();
});
