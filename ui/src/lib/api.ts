export const API_URL = import.meta.env.VITE_API_URL || "";

const API_KEY_STORAGE = "orion_api_key";

export function getStoredApiKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setStoredApiKey(value: string): void {
  if (typeof window === "undefined") return;
  const normalized = value.trim();
  if (normalized) window.localStorage.setItem(API_KEY_STORAGE, normalized);
  else window.localStorage.removeItem(API_KEY_STORAGE);
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const apiKey = getStoredApiKey();
  if (apiKey && !headers.has("Authorization") && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", apiKey);
  }
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
      else if (parsed.detail) message = JSON.stringify(parsed.detail);
    } catch {
      // Keep non-JSON upstream error text.
    }
    throw new Error(message || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}
