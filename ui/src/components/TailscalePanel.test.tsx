import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const { check, internet } = vi.hoisted(() => ({ check: vi.fn(), internet: vi.fn() }));
vi.mock("@/lib/server-profiles", async (original) => ({
  ...(await original<typeof import("@/lib/server-profiles")>()),
  desktopTailscaleStatus: () => check,
  desktopTailscaleToggle: () => undefined,
  desktopInternetToggle: () => internet,
  activeHostStop: () => undefined,
}));
import { TailscalePanel } from "./ServerConnections";

it("requires explicit consent for public access and disables it without another consent", async () => {
  const privateStatus = {
    state: "configured",
    reachable: true,
    url: "https://fixture.ts.net",
    enabled: true,
  };
  let status = privateStatus;
  check.mockImplementation(async () => status);
  internet.mockImplementation(async (enabled) => {
    status = { ...privateStatus, state: enabled ? "public" : "configured" };
    return status;
  });
  render(<TailscalePanel />);
  const enable = await screen.findByRole("button", { name: "Bật truy cập qua Internet" });
  await waitFor(() => expect(screen.getByText(/Serve đã trỏ/)).toBeTruthy());
  expect(enable.hasAttribute("disabled")).toBe(true);
  expect(internet).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Bật truy cập qua Internet" }));
  await screen.findByRole("button", { name: "Tắt truy cập qua Internet" });
  expect(internet).toHaveBeenCalledWith(true, true);
  fireEvent.click(screen.getByRole("button", { name: "Tắt truy cập qua Internet" }));
  await screen.findByRole("button", { name: "Bật truy cập qua Internet" });
  expect(internet).toHaveBeenLastCalledWith(false, false);
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
});
