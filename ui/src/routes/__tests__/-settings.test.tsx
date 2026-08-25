import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "@/routes/settings";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("M1 model settings", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("loads the active M1 model and posts only the current configuration contract", async () => {
    let modelConfigured = false;
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/integrations/internet") {
        return Promise.resolve(
          jsonResponse({
            status: "unconfigured",
            provider: null,
            endpoint: null,
            message: "Internet search is not configured.",
          }),
        );
      }
      if (path.startsWith("/api/integrations/")) {
        return Promise.resolve(
          jsonResponse({ status: "unconfigured", message: "Not configured." }),
        );
      }
      if (path === "/api/models" && init?.method === "POST") {
        modelConfigured = true;
        return Promise.resolve(
          jsonResponse({
            model_config_id: "cfg-1",
            provider_type: "openai_compatible",
            base_url: "https://api.openai.com/v1",
            model_id: "gpt-4.1",
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(
          modelConfigured
            ? [
                {
                  model_config_id: "cfg-1",
                  provider_type: "openai_compatible",
                  base_url: "https://api.openai.com/v1",
                  model_id: "gpt-4.1",
                },
              ]
            : [],
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);
    await screen.findByText("Chưa cấu hình model.");
    fireEvent.change(screen.getByPlaceholderText(/Base URL/), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText("Model name"), {
      target: { value: "gpt-4.1" },
    });
    fireEvent.change(screen.getByPlaceholderText(/API key/), {
      target: { value: "provider-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu model" }));

    await screen.findByText("Đã lưu cấu hình model.");
    const [path, init] = fetchMock.mock.calls.find(
      ([requestPath, requestInit]) =>
        requestPath === "/api/models" && requestInit?.method === "POST",
    ) as [string, RequestInit];
    expect(path).toBe("/api/models");
    expect(JSON.parse(String(init.body))).toEqual({
      provider_type: "openai_compatible",
      base_url: "https://api.openai.com/v1",
      model_id: "gpt-4.1",
      api_key: "provider-secret",
    });
    expect(window.localStorage.getItem("orion_api_key")).toBeNull();
    await screen.findByText("Internet search is not configured.");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7));
  });

  it("does not show a configured-but-unhealthy Internet integration as ready", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/integrations/internet") {
        return Promise.resolve(
          jsonResponse({
            status: "unhealthy",
            provider: "searxng",
            endpoint: "https://search.test/api",
            message: "Configured Internet search integration is currently unavailable.",
          }),
        );
      }
      if (path.startsWith("/api/integrations/")) {
        return Promise.resolve(
          jsonResponse({ status: "unconfigured", message: "Not configured." }),
        );
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    await screen.findByText("Không khả dụng");
    expect(screen.queryByText("Sẵn sàng")).toBeNull();
    expect(
      screen.getByText("Configured Internet search integration is currently unavailable."),
    ).toBeTruthy();
  });
});
