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
      if (path === "/api/models" && init?.method === "POST") {
        modelConfigured = true;
        return Promise.resolve(
          jsonResponse({
            model_config_id: "cfg-1",
            provider_type: "openai_compatible",
            base_url: "https://api.openai.com/v1",
            model_id: "gpt-4.1",
            reasoning_mode: "auto",
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
                  reasoning_mode: "auto",
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
      reasoning_mode: "auto",
    });
    expect(window.localStorage.getItem("orion_api_key")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit gpt-4.1" }));
    expect((screen.getByLabelText("Reasoning mode") as HTMLSelectElement).value).toBe("auto");
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([path]) => path === "/api/models")).toHaveLength(3),
    );
  });

  it("manages multiple saved models, including switching and editing without sending a blank key", async () => {
    let models = [
      {
        model_config_id: "cfg-a",
        provider_type: "openai_compatible",
        base_url: "http://qwen.test/v1",
        model_id: "qwen3-32b",
        reasoning_mode: "auto",
        is_active: true,
      },
      {
        model_config_id: "cfg-b",
        provider_type: "openai_compatible",
        base_url: "http://llama.test/v1",
        model_id: "llama-3.3",
        reasoning_mode: "disabled",
        is_active: false,
      },
    ];
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
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
    fireEvent.click(screen.getByRole("button", { name: "Edit llama-3.3" }));
    expect((screen.getByLabelText("Reasoning mode") as HTMLSelectElement).value).toBe("disabled");
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
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
      reasoning_mode: "auto",
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete qwen3-32b-updated" }));

    await screen.findByText("Đã xóa model đã lưu.");
    expect(fetchMock).toHaveBeenCalledWith("/api/models/cfg-a", expect.anything());
  });

  it("loads configuration metadata without starting a model, MCP connection or tool", async () => {
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (
        ["/api/models", "/api/sessions", "/api/mcp/servers", "/api/auth/native/sessions"].includes(
          path,
        )
      )
        return Promise.resolve(jsonResponse([]));
      if (path === "/api/doctor")
        return Promise.resolve(
          jsonResponse({
            observation: "configuration",
            model_profile_configured: false,
            mcp_connected: 0,
            mcp_configured: 0,
            active_requests: 0,
          }),
        );
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SettingsPage />);

    await screen.findByText(/Đây là thiết lập Orion lần đầu/);
    expect(screen.queryByText("Tích hợp")).toBeNull();
    expect(new Set(fetchMock.mock.calls.map(([path]) => path))).toEqual(
      new Set([
        "/api/models",
        "/api/sessions",
        "/api/mcp/servers",
        "/api/auth/native/sessions",
        "/api/doctor",
      ]),
    );
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(
      true,
    );
    expect(screen.getByRole("region", { name: "Runtime resources" })).toBeTruthy();
  });

  it.each([
    ["deepseek", "chat_completions"],
    ["claude", "anthropic_messages"],
    ["openai", "openai_responses"],
  ])("saves a typed %s profile with a server credential reference", async (provider, protocol) => {
    const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/models" && init?.method === "POST")
        return jsonResponse({
          model_config_id: "new",
          provider_type: provider,
          base_url: "https://provider.test",
          model_id: "owner-model",
          reasoning_mode: "auto",
          is_active: true,
        });
      if (path === "/api/doctor")
        return jsonResponse({
          observation: "configuration",
          mcp_connected: 0,
          mcp_configured: 0,
          active_requests: 0,
        });
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<SettingsPage />);
    await screen.findByText(/Đây là thiết lập Orion lần đầu/);
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: provider } });
    fireEvent.change(screen.getByPlaceholderText(/Base URL/), {
      target: { value: "https://provider.test" },
    });
    fireEvent.change(screen.getByPlaceholderText("Model name"), {
      target: { value: "owner-model" },
    });
    fireEvent.change(screen.getByLabelText("Credential reference trên server"), {
      target: { value: "env:OWNER_PROVIDER_KEY" },
    });
    expect(screen.queryByPlaceholderText(/API key/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Lưu model" }));
    await screen.findByText("Đã lưu cấu hình model.");
    const call = fetcher.mock.calls.find(
      ([path, init]) => path === "/api/models" && init?.method === "POST",
    )!;
    const body = JSON.parse(String(call[1]?.body));
    expect(body.provider_type).toBe(provider);
    expect(body.profile).toMatchObject({
      provider_id: provider,
      protocol,
      model_id: "owner-model",
      credential_ref: "env:OWNER_PROVIDER_KEY",
      capabilities: { text: true, tools: false, streaming: false },
    });
    expect(body).not.toHaveProperty("api_key");
    expect(localStorage.getItem("orion_api_key")).toBeNull();
  });
});
