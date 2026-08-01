import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "@/routes/settings";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("model settings", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("saves and immediately tests a manual model connection", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ active_server: "", models: [] }))
      .mockResolvedValueOnce(jsonResponse({ active_server: "primary", models: [] }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok", name: "primary" }))
      .mockResolvedValueOnce(jsonResponse({ active_server: "primary", models: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);
    await screen.findByText("Chưa cấu hình model.");

    fireEvent.change(screen.getByPlaceholderText(/Base URL/), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("Model name"), {
      target: { value: "gpt-4.1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Lưu & kiểm tra/ }));

    await screen.findByText(/kiểm tra kết nối model thành công/);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/models");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/models/primary/test");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
  });

  it("keeps a failed connection saved and shows the test error", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ active_server: "", models: [] }))
      .mockResolvedValueOnce(jsonResponse({ active_server: "primary", models: [] }))
      .mockResolvedValueOnce(jsonResponse({ detail: "connection refused" }, 503))
      .mockResolvedValueOnce(jsonResponse({ active_server: "primary", models: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);
    await screen.findByText("Chưa cấu hình model.");
    fireEvent.change(screen.getByPlaceholderText(/Base URL/), {
      target: { value: "http://model:8000" },
    });
    fireEvent.change(screen.getByPlaceholderText("Model name"), {
      target: { value: "qwen" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Lưu & kiểm tra/ }));

    expect(await screen.findByText(/connection refused/)).toBeTruthy();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
  });
});
