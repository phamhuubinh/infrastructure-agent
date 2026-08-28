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
            is_active: true,
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
                  is_active: true,
                },
              ]
            : [],
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);
    await screen.findByText(/Đây là thiết lập Orion lần đầu/);
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

  it("manages multiple saved models, including switching and editing without sending a blank key", async () => {
    let models = [
      {
        model_config_id: "cfg-a",
        provider_type: "openai_compatible",
        base_url: "http://qwen.test/v1",
        model_id: "qwen3-32b",
        is_active: true,
      },
      {
        model_config_id: "cfg-b",
        provider_type: "openai_compatible",
        base_url: "http://llama.test/v1",
        model_id: "llama-3.3",
        is_active: false,
      },
    ];
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/integrations/internet") {
        return Promise.resolve(
          jsonResponse({ status: "unconfigured", provider: null, endpoint: null, message: "No" }),
        );
      }
      if (path.startsWith("/api/integrations/")) {
        return Promise.resolve(jsonResponse({ status: "unconfigured", message: "No" }));
      }
      if (path === "/api/models/cfg-b/activate" && init?.method === "POST") {
        models = models.map((model) => ({
          ...model,
          is_active: model.model_config_id === "cfg-b",
        }));
        return Promise.resolve(jsonResponse(models[1]));
      }
      if (path === "/api/models/cfg-a" && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { base_url: string; model_id: string };
        models = models.map((model) =>
          model.model_config_id === "cfg-a"
            ? { ...model, base_url: body.base_url, model_id: body.model_id }
            : model,
        );
        return Promise.resolve(jsonResponse(models[0]));
      }
      if (path === "/api/models/cfg-a" && init?.method === "DELETE") {
        models = models.filter((model) => model.model_config_id !== "cfg-a");
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (path === "/api/models") return Promise.resolve(jsonResponse(models));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);
    await screen.findByText("qwen3-32b");
    expect(screen.getByText("Đang dùng")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dùng model này" }));

    await screen.findByText("Đã chọn model đang dùng.");
    expect(fetchMock).toHaveBeenCalledWith("/api/models/cfg-b/activate", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Edit qwen3-32b" }));
    fireEvent.change(screen.getByPlaceholderText("Model name"), {
      target: { value: "qwen3-32b-updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    await screen.findByText("Đã cập nhật cấu hình model.");
    const [, updateInit] = fetchMock.mock.calls.find(
      ([requestPath, requestInit]) =>
        requestPath === "/api/models/cfg-a" && requestInit?.method === "PUT",
    ) as [string, RequestInit];
    expect(JSON.parse(String(updateInit.body))).toEqual({
      provider_type: "openai_compatible",
      base_url: "http://qwen.test/v1",
      model_id: "qwen3-32b-updated",
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete qwen3-32b-updated" }));

    await screen.findByText("Đã xóa model đã lưu.");
    expect(fetchMock).toHaveBeenCalledWith("/api/models/cfg-a", expect.anything());
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

  it("presents independent read-only integration availability without tool controls", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/models") return Promise.resolve(jsonResponse([]));
      if (path === "/api/integrations/internet")
        return Promise.resolve(
          jsonResponse({ status: "healthy", provider: "searxng", endpoint: null, message: null }),
        );
      if (path === "/api/integrations/linux")
        return Promise.resolve(
          jsonResponse({ status: "unconfigured", message: "Linux is not configured." }),
        );
      if (path === "/api/integrations/grafana")
        return Promise.resolve(
          jsonResponse({ status: "unhealthy", message: "Grafana is unavailable." }),
        );
      if (path === "/api/integrations/zabbix")
        return Promise.resolve(jsonResponse({ status: "healthy", message: null }));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SettingsPage />);

    await screen.findByText("Tích hợp");
    expect(screen.getByText(/Orion tự sử dụng các công cụ khả dụng khi model cần/)).toBeTruthy();
    expect(screen.getByText("Internet")).toBeTruthy();
    expect(screen.getByText("Linux")).toBeTruthy();
    expect(screen.getByText("Grafana")).toBeTruthy();
    expect(screen.getByText("Zabbix")).toBeTruthy();
    expect(screen.getAllByText("Sẵn sàng")).toHaveLength(2);
    expect(screen.getByText("Chưa cấu hình")).toBeTruthy();
    expect(screen.getByText("Không khả dụng")).toBeTruthy();
    expect(screen.queryByText(/Bật tool|Tắt tool|enabled_tools/i)).toBeNull();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("refreshes integrations independently without reloading model profiles", async () => {
    let refresh = false;
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/models") return Promise.resolve(jsonResponse([]));
      if (path === "/api/integrations/internet")
        return Promise.resolve(
          jsonResponse({ status: "healthy", provider: null, endpoint: null, message: null }),
        );
      if (path === "/api/integrations/linux")
        return Promise.resolve(jsonResponse({ status: "healthy", message: null }));
      if (path === "/api/integrations/grafana") {
        return refresh
          ? Promise.reject(new Error("offline"))
          : Promise.resolve(jsonResponse({ status: "healthy", message: null }));
      }
      if (path === "/api/integrations/zabbix")
        return Promise.resolve(jsonResponse({ status: "unconfigured", message: null }));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SettingsPage />);
    await screen.findByText("Grafana");
    refresh = true;
    fireEvent.click(screen.getByRole("button", { name: "Làm mới trạng thái" }));
    await screen.findByText("Không thể tải trạng thái tích hợp.");
    expect(screen.getByText("Internet")).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/models")).toHaveLength(1);
  });
});
