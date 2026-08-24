export const API_URL = import.meta.env.VITE_API_URL || "";

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export async function apiErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  let message = body;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") message = parsed.detail;
    else if (parsed.detail) message = JSON.stringify(parsed.detail);
  } catch {
    // Keep non-JSON upstream error text.
  }

  return message || `Request failed (${response.status})`;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response));
  }
  return (await response.json()) as T;
}
