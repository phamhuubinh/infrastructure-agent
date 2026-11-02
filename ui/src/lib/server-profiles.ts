import { ClientError, OrionClient, type SecureTokenStore } from "./sdk/client";
import { type OperationId, type Operations } from "./sdk/generated";

export const SERVER_CHANGED_EVENT = "orion-server-changed";
export type ServerProfile = { id: string; name: string; origin: string };
export type NativeHost = {
  fetch: typeof fetch;
  tokens: SecureTokenStore;
  platform: "windows" | "linux" | "android" | "ios";
};
const storageKey = "orion-server-profiles-v1";
let nativeHost: NativeHost | null = null;
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
  nativeHost = host;
}

export function isNativeHost() {
  return nativeHost !== null;
}
export function activeServer(): ServerProfile {
  return selected ?? { id: "browser", name: "Server hiện tại", origin: window.location.origin };
}

function canonical(profile: ServerProfile): ServerProfile {
  if (
    typeof profile.id !== "string" ||
    typeof profile.name !== "string" ||
    typeof profile.origin !== "string" ||
    !profile.id ||
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
  const profile = canonical({ id: crypto.randomUUID(), name, origin });
  if (profiles.some((item) => item.origin === profile.origin))
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
  if (!nativeHost && next.origin !== window.location.origin) {
    // Browser sessions remain bound to their server origin; no cross-origin cookie/CORS bypass.
    window.location.assign(next.origin);
    return;
  }
  lifetime.abort();
  client?.dispose();
  lifetime = new AbortController();
  selected = next;
  client = null;
  window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
}

export function serverClient(): OrionClient {
  if (!client) {
    const origin = activeServer().origin;
    client = nativeHost
      ? new OrionClient({ origin, mode: "native", ...nativeHost })
      : new OrionClient({
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
  if (!nativeHost) throw new ClientError("configuration");
  await serverClient().enroll(code, name, nativeHost.platform);
  window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
}

export async function logoutServer() {
  lifetime.abort();
  lifetime = new AbortController();
  try {
    await serverClient().logout();
  } finally {
    window.dispatchEvent(new Event(SERVER_CHANGED_EVENT));
  }
}
