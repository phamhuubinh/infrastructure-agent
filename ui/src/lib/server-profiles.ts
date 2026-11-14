import { newUuid } from "./uuid";
import { ClientError, OrionClient, type SecureTokenStore } from "./sdk/client";
import { type OperationId, type Operations } from "./sdk/generated";

export const SERVER_CHANGED_EVENT = "orion-server-changed";
export type ServerProfile = { id: string; name: string; origin: string };
export type NativeHost = {
  fetch: typeof fetch;
  tokens: SecureTokenStore;
  platform: "windows" | "linux" | "android" | "ios";
  hostOrigin?: string;
  stopHost?: () => Promise<void>;
  managedError?: string;
  managedBackend?: { origin: string; fetch: typeof fetch };
};
const storageKey = "orion-server-profiles-v1";
const managedId = "orion-managed-local";
let nativeHost: NativeHost | null = null;
let managedServer: ServerProfile | null = null;
let selected: ServerProfile | null = null;
let client: OrionClient | null = null;
let lifetime = new AbortController();
export function serverContext(): AbortSignal {
  return lifetime.signal;
}

window.addEventListener("orion-auth-expired", () => {
  lifetime.abort();
  client?.dispose();
  client = null;
  lifetime = new AbortController();
});

/** Called by the trusted platform entry, never inferred from user agents or localStorage. */
export function installNativeHost(host: NativeHost) {
  if (client || nativeHost) throw new ClientError("configuration");
  if (host.managedBackend) {
    const origin = new OrionClient({ origin: host.managedBackend.origin, mode: "browser" }).origin;
    if (
      host.platform !== "windows" ||
      !/^http:\/\/127\.0\.0\.1:\d+$/.test(origin) ||
      typeof host.managedBackend.fetch !== "function"
    ) {
      throw new ClientError("configuration");
    }
    managedServer = { id: managedId, name: "Orion trên máy này", origin };
  }
  nativeHost = host;
}

export function isNativeHost() {
  return nativeHost !== null;
}

export function isMobileHost() {
  return nativeHost?.platform === "android" || nativeHost?.platform === "ios";
}

export function hasActiveServer() {
  return !nativeHost || selected !== null || managedServer !== null;
}

export function activeServer(): ServerProfile {
  return (
    selected ??
    managedServer ?? { id: "browser", name: "Server hiện tại", origin: window.location.origin }
  );
}

export function activeHostOrigin() {
  return nativeHost?.hostOrigin;
}

export function activeHostStop() {
  return nativeHost?.stopHost;
}

export function managedServerError() {
  return nativeHost?.managedError;
}

export function hasManagedServer() {
  return managedServer !== null;
}

export function isManagedServer() {
  return managedServer !== null && selected === null;
}

function canonical(profile: ServerProfile): ServerProfile {
  if (
    typeof profile.id !== "string" ||
    typeof profile.name !== "string" ||
    typeof profile.origin !== "string" ||
    !profile.id ||
    profile.id === managedId ||
    profile.id.length > 128 ||
    !profile.name.trim() ||
    profile.name.length > 120
  ) {
    throw new ClientError("configuration");
  }
  return {
    id: profile.id,
    name: profile.name.trim(),
    origin: new OrionClient({ origin: profile.origin, mode: "browser" }).origin,
  };
}

export function serverProfiles(): ServerProfile[] {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw || raw.length > 32768) return [];
    const values: unknown = JSON.parse(raw);
    if (!Array.isArray(values) || values.length > 16) return [];
    const result = values.map((value) => canonical(value));
    if (new Set(result.map((profile) => profile.id)).size !== result.length) return [];
    return result;
  } catch {
    return [];
  }
}

export function saveServerProfile(name: string, origin: string): ServerProfile {
  const profiles = serverProfiles();
  if (profiles.length >= 16) throw new ClientError("configuration");
  const profile = canonical({ id: newUuid(), name, origin });
  if (
    profile.origin === managedServer?.origin ||
    profiles.some((item) => item.origin === profile.origin)
  )
    throw new ClientError("configuration");
  localStorage.setItem(storageKey, JSON.stringify([...profiles, profile]));
  return profile;
}

export function removeServerProfile(id: string) {
  if (selected?.id === id) throw new ClientError("configuration");
  localStorage.setItem(
    storageKey,
    JSON.stringify(serverProfiles().filter((profile) => profile.id !== id)),
  );
}

export function activateServer(profile: ServerProfile) {
  const next = canonical(profile);
  if (next.origin === managedServer?.origin) throw new ClientError("configuration");
  if (!nativeHost && next.origin !== window.location.origin) {
    // Browser sessions remain bound to their server origin; no cross-origin cookie/CORS bypass.
    window.location.assign(next.origin);
    return;
  }
  selectServer(next);
}

export function activateManagedServer() {
  if (!managedServer) throw new ClientError("configuration");
  selectServer(null);
}

function selectServer(next: ServerProfile | null) {
  lifetime.abort();
  client?.dispose();
  lifetime = new AbortController();
  selected = next;
  client = null;
  window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
}

export function serverClient(): OrionClient {
  if (!hasActiveServer()) throw new ClientError("configuration");
  if (client) return client;
  const origin = activeServer().origin;
  if (nativeHost) {
    const managed = isManagedServer() ? nativeHost.managedBackend : undefined;
    client = managed
      ? new OrionClient({ origin, mode: "managed", fetch: managed.fetch })
      : new OrionClient({
          origin,
          mode: "native",
          fetch: nativeHost.fetch,
          tokens: nativeHost.tokens,
        });
  } else {
    client = new OrionClient({
      origin,
      mode: "browser",
      fetch: async (url, init) => {
        const target = new URL(String(url));
        if (target.origin !== window.location.origin) throw new ClientError("configuration");
        return globalThis.fetch(target.pathname + target.search, {
          ...init,
          method: init?.method === "GET" ? undefined : init?.method,
        });
      },
    });
  }
  return client;
}

export async function serverRequest<K extends OperationId>(
  operation: K,
  input: Operations[K]["input"],
  signal?: AbortSignal,
): Promise<Operations[K]["output"]> {
  const epoch = lifetime;
  let result: Operations[K]["output"];
  try {
    result = await serverClient().request(
      operation,
      input,
      signal ? AbortSignal.any([signal, lifetime.signal]) : lifetime.signal,
    );
  } catch (error) {
    if (epoch !== lifetime) throw new ClientError("cancelled");
    if (epoch === lifetime && error instanceof ClientError && error.category === "authentication") {
      window.dispatchEvent(new Event("orion-auth-expired"));
    }
    throw error;
  }
  if (epoch !== lifetime) throw new ClientError("cancelled");
  return result;
}

export async function serverResponse<K extends OperationId>(
  operation: K,
  input: Operations[K]["input"],
  signal?: AbortSignal,
): Promise<Response> {
  const epoch = lifetime;
  let response: Response;
  try {
    response = await serverClient().response(
      operation,
      input,
      signal ? AbortSignal.any([signal, lifetime.signal]) : lifetime.signal,
    );
  } catch (error) {
    if (epoch !== lifetime) throw new ClientError("cancelled");
    throw error;
  }
  if (epoch !== lifetime) {
    await response.body?.cancel().catch(() => {});
    throw new ClientError("cancelled");
  }
  return response;
}

export async function enrollServer(code: string, name: string) {
  if (!nativeHost || isManagedServer()) throw new ClientError("configuration");
  await serverClient().enroll(code, name, nativeHost.platform);
  window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
}

export async function logoutServer() {
  if (isManagedServer()) throw new ClientError("configuration");
  lifetime.abort();
  lifetime = new AbortController();
  try {
    await serverClient().logout();
  } finally {
    window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
  }
}
