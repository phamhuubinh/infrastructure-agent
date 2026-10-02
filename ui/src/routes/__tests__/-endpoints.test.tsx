import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EndpointsPage } from "../endpoints";

vi.mock("@tanstack/react-router", () => ({ createFileRoute: () => () => ({}) }));
vi.mock("@/components/chat/DeviceChat", () => ({ DeviceChat: () => <p>Device Chat isolated</p> }));
const mocks = vi.hoisted(() => ({ json: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiJson: mocks.json, apiFetch: mocks.fetch }));
const device = {
  endpoint_id: "a".repeat(32),
  name: "Test Windows",
  platform: "windows",
  online: true,
  revoked_at: null,
  capabilities: ["screen.capture", "desktop.click"],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("Endpoints", () => {
  it("offers exact-version portable downloads with checksum and a separate endpoint workspace", async () => {
    mocks.json.mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("artifacts")
          ? {
              available: true,
              version: "0.1.3",
              artifacts: [
                {
                  platform: "windows-x64",
                  url: "https://github.com/example/windows.zip",
                  sha256: "1".repeat(64),
                },
                {
                  platform: "linux-x86_64",
                  url: "https://github.com/example/linux.tar.gz",
                  sha256: "2".repeat(64),
                },
              ],
            }
          : [device],
      ),
    );
    render(<EndpointsPage />);
    expect((await screen.findByText("Download Windows portable worker")).getAttribute("href")).toBe(
      "https://github.com/example/windows.zip",
    );
    expect(screen.getByText("Download Linux portable worker")).toBeTruthy();
    expect(screen.getByText("1".repeat(64))).toBeTruthy();
    fireEvent.click(await screen.findByText(/Test Windows · windows · Online/));
    expect(screen.getByText("Device Chat isolated")).toBeTruthy();
    for (const tab of ["Chat", "Desktop", "Files", "Processes", "Browser", "Connection"])
      expect(screen.getByRole("tab", { name: tab })).toBeTruthy();
    expect(screen.queryByLabelText("Attach document")).toBeNull();
  });

  it("shows unavailable development artifacts and only calls operations for the selected endpoint", async () => {
    mocks.json.mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("artifacts")
          ? { available: false, version: "dev", artifacts: [] }
          : url.endsWith("operation")
            ? { processes: [] }
            : [device],
      ),
    );
    render(<EndpointsPage />);
    expect(await screen.findByText("Artifact unavailable for this build")).toBeTruthy();
    fireEvent.click(await screen.findByText(/Test Windows · windows · Online/));
    fireEvent.click(screen.getByRole("tab", { name: "Processes" }));
    fireEvent.click(screen.getByText("Liệt kê tiến trình"));
    await waitFor(() =>
      expect(mocks.json).toHaveBeenCalledWith(
        `/api/endpoints/${device.endpoint_id}/operation`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ operation: "process.list", arguments: {} }),
        }),
      ),
    );
  });
  it("lists safe device identities, online/detail and offline state", async () => {
    mocks.json.mockResolvedValue([device]);
    render(<EndpointsPage />);
    fireEvent.click(await screen.findByText(/Test Windows · windows · Online/));
    expect(screen.getByLabelText("Chi tiết thiết bị")).toBeTruthy();
    expect(screen.getByText(device.endpoint_id)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Desktop" }));
    expect(screen.getByText("Chưa mở phiên màn hình")).toBeTruthy();
    mocks.json.mockResolvedValue([{ ...device, online: false }]);
    expect(localStorage.getItem("desktop-session")).toBeNull();
  });

  it("pairing token is ephemeral and can be hidden", async () => {
    mocks.json.mockImplementation((url: string) =>
      Promise.resolve(url.endsWith("pairing-tokens") ? { token: "one-time-secret" } : [device]),
    );
    render(<EndpointsPage />);
    fireEvent.click(screen.getByText("Tạo mã ghép nối tạm thời"));
    expect(await screen.findByText("one-time-secret")).toBeTruthy();
    expect(localStorage.getItem("pairing-token")).toBeNull();
    fireEvent.click(screen.getByText("Ẩn mã"));
    expect(screen.queryByText("one-time-secret")).toBeNull();
  });

  it("starts view, enables explicit control, stops on stream disconnect", async () => {
    let stream: ReadableStreamDefaultController<Uint8Array>;
    mocks.json.mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("desktop/session")
          ? { session_id: "b".repeat(32), control_available: true }
          : url.endsWith("desktop/control")
            ? { enabled: true }
            : [device],
      ),
    );
    mocks.fetch.mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            stream = controller;
          },
        }),
      ),
    );
    render(<EndpointsPage />);
    fireEvent.click(await screen.findByText(/Test Windows · windows · Online/));
    fireEvent.click(screen.getByRole("tab", { name: "Desktop" }));
    fireEvent.click(screen.getByText("Xem màn hình"));
    await screen.findByText("Đã kết nối · Chỉ xem");
    fireEvent.click(screen.getByText("Bật điều khiển"));
    await screen.findByText("Đã kết nối · Điều khiển bật");
    await act(async () => stream!.close());
    await waitFor(() => expect(screen.getByText("Chưa mở phiên màn hình")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toContain("ngắt kết nối");
  });
});
