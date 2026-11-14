import { afterEach, beforeEach, expect, it, vi } from "vitest";

const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

const origin = "http://127.0.0.1:49821";

beforeEach(() => invoke.mockReset());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

it.each(["android", "ios"])("installs a %s host in remote-only mode", async (platform) => {
  const { installTauriHost } = await import("../tauri-host");
  const { isMobileHost, hasManagedServer, hasActiveServer } = await import("../server-profiles");
  invoke.mockResolvedValueOnce({ platform, managedOrigin: null });
  await installTauriHost();
  expect(isMobileHost()).toBe(true);
  expect(hasManagedServer()).toBe(false);
  expect(hasActiveServer()).toBe(false);
});

it.each(["android", "ios"])(
  "uses JSON-safe bytes for %s IPC and the selected origin's bearer",
  async (platform) => {
    const { installTauriHost } = await import("../tauri-host");
    const { activateServer, serverResponse } = await import("../server-profiles");
    const remote = "https://orion.example";
    const accessToken = "orion_access_" + "a".repeat(43);
    invoke.mockResolvedValueOnce({ platform, managedOrigin: null });
    invoke.mockResolvedValueOnce({
      session_id: "a".repeat(32),
      token_type: "Bearer",
      access_token: accessToken,
      refresh_token: "orion_refresh_" + "b".repeat(43),
      access_expires_at: 2000000000,
      refresh_expires_at: 2001000000,
    });
    invoke.mockResolvedValueOnce(undefined);
    invoke.mockResolvedValueOnce({ status: 200, headers: [["content-type", "application/json"]] });
    invoke.mockResolvedValueOnce(btoa("{}"));
    invoke.mockResolvedValueOnce("");
    invoke.mockResolvedValueOnce(undefined);
    if (platform === "ios") {
      vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
    }
    await installTauriHost();
    activateServer({ id: "remote", name: "Remote", origin: remote });
    const body = { content: "Đã kết nối", client_request_id: "fixture-request" };
    const response = await serverResponse("admit_api_sessions__session_id__requests_post", {
      path: { session_id: "fixture-session" },
      body,
    });
    expect(await response.json()).toEqual({});
    expect(invoke).toHaveBeenNthCalledWith(2, "orion_vault_get", { origin: remote });
    const { id, request } = invoke.mock.calls[2][1];
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(request).toMatchObject({
      origin: remote,
      managed: false,
      headers: [
        ["authorization", "Bearer " + accessToken],
        ["content-type", "application/json"],
      ],
    });
    const [command, payload] = invoke.mock.calls[3];
    expect(command).toBe("orion_start_mobile");
    expect(payload.id).toBe(id);
    const decoded = Uint8Array.from(atob(payload.body), (byte) => byte.charCodeAt(0));
    expect(new TextDecoder().decode(decoded)).toBe(JSON.stringify(body));
    expect(invoke).toHaveBeenCalledWith("orion_read_mobile", { id });
  },
);

it("retains the Windows startup error and supports choosing a remote server", async () => {
  const { installTauriHost } = await import("../tauri-host");
  const { activateServer, activeServer, hasActiveServer, managedServerError } =
    await import("../server-profiles");
  const managedError = "Backend cục bộ khởi động quá thời gian chờ.";
  invoke.mockResolvedValueOnce({ platform: "windows", managedOrigin: null, managedError });
  await installTauriHost();
  expect(managedServerError()).toBe(managedError);
  expect(hasActiveServer()).toBe(false);
  const remote = { id: "remote", name: "Remote", origin: "https://orion.example" };
  activateServer(remote);
  expect(activeServer()).toEqual(remote);
});

it("sends managed requests as raw IPC and returns a streamed response", async () => {
  const { installTauriHost } = await import("../tauri-host");
  const { serverResponse } = await import("../server-profiles");
  const bytes = new TextEncoder().encode("{}").buffer;
  invoke.mockResolvedValueOnce({ managedOrigin: origin });
  invoke.mockResolvedValueOnce(undefined);
  invoke.mockResolvedValueOnce({ status: 200, headers: [["content-type", "application/json"]] });
  invoke.mockResolvedValueOnce(bytes);
  invoke.mockResolvedValueOnce(new ArrayBuffer(0));
  invoke.mockResolvedValueOnce(undefined);

  await installTauriHost();
  const body = { content: "Fixture", client_request_id: "fixture-request" };
  const response = await serverResponse("admit_api_sessions__session_id__requests_post", {
    path: { session_id: "fixture-session" },
    body,
  });
  expect(await response.json()).toEqual({});
  const { id } = invoke.mock.calls[1][1];
  expect(invoke).toHaveBeenNthCalledWith(2, "orion_prepare", {
    id,
    request: {
      managed: true,
      origin,
      url: `${origin}/api/sessions/fixture-session/requests`,
      method: "POST",
      headers: [["content-type", "application/json"]],
    },
  });
  const [command, raw, options] = invoke.mock.calls[2];
  expect(command).toBe("orion_start");
  expect(ArrayBuffer.isView(raw)).toBe(true);
  expect(new TextDecoder().decode(raw)).toBe(JSON.stringify(body));
  expect(options).toEqual({ headers: { "x-orion-request": id } });
  expect(invoke).toHaveBeenLastCalledWith("orion_close", { id });
});

it("closes an in-flight native request when its SDK signal is aborted", async () => {
  const { installTauriHost } = await import("../tauri-host");
  const { serverResponse } = await import("../server-profiles");
  let rejectStart!: (reason: Error) => void;
  invoke.mockImplementation(async (command) => {
    if (command === "orion_host") return { managedOrigin: origin };
    if (command === "orion_start") {
      return new Promise((_, reject) => {
        rejectStart = reject;
      });
    }
    if (command === "orion_close") rejectStart(new Error("native request closed"));
    return undefined;
  });
  await installTauriHost();
  const controller = new AbortController();
  const response = serverResponse("doctor_api_doctor_get", {}, controller.signal);
  const cancelled = expect(response).rejects.toThrow("cancelled");
  await vi.waitFor(() => expect(invoke).toHaveBeenCalledTimes(3));
  controller.abort();
  await cancelled;
  expect(invoke).toHaveBeenLastCalledWith("orion_close", { id: invoke.mock.calls[1][1].id });
});
