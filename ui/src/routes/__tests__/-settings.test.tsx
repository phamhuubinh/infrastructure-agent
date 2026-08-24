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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({
          model_config_id: "cfg-1",
          provider_type: "openai_compatible",
          base_url: "https://api.openai.com/v1",
          model_id: "gpt-4.1",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            model_config_id: "cfg-1",
            provider_type: "openai_compatible",
            base_url: "https://api.openai.com/v1",
            model_id: "gpt-4.1",
          },
        ]),
      );
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
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/models");
    expect(JSON.parse(String(init.body))).toEqual({
      provider_type: "openai_compatible",
      base_url: "https://api.openai.com/v1",
      model_id: "gpt-4.1",
      api_key: "provider-secret",
    });
    expect(window.localStorage.getItem("orion_api_key")).toBeNull();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });
});
