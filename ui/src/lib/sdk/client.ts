import { operations, type OperationId, type Operations, type Schemas } from "./generated";

export type TokenPair = Schemas["NativeTokenPair"];

/** Native hosts implement this with their OS credential vault, scoped by server origin. */
export interface SecureTokenStore {
  get(origin: string): Promise<TokenPair | null>;
  set(origin: string, pair: TokenPair): Promise<void>;
  clear(origin: string): Promise<void>;
}

type Options =
  | { origin: string; mode: "browser"; fetch?: typeof fetch }
  | {
      origin: string;
      mode: "native";
      fetch: typeof fetch;
      tokens: SecureTokenStore;
    };

export class ClientError extends Error {
  constructor(
    readonly category: "configuration" | "authentication" | "network" | "response" | "cancelled",
    readonly status?: number,
  ) {
    super(`Orion client ${category} error`);
  }
}

function serverOrigin(raw: string): string {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new ClientError("configuration");
  }
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/" ||
    (url.protocol !== "https:" &&
      !(url.protocol === "http:" && ["127.0.0.1", "[::1]"].includes(url.hostname)))
  ) {
    throw new ClientError("configuration");
  }
  return url.origin;
}

function tokenPair(value: unknown): TokenPair {
  const row = value as Partial<TokenPair> | null;
  if (
    !row ||
    row.token_type !== "Bearer" ||
    typeof row.session_id !== "string" ||
    !/^[0-9a-f]{32}$/.test(row.session_id) ||
    typeof row.access_token !== "string" ||
    !/^orion_access_[A-Za-z0-9_-]{43}$/.test(row.access_token) ||
    typeof row.refresh_token !== "string" ||
    !/^orion_refresh_[A-Za-z0-9_-]{43}$/.test(row.refresh_token) ||
    !Number.isSafeInteger(row.access_expires_at) ||
    !Number.isSafeInteger(row.refresh_expires_at)
  ) {
    throw new ClientError("authentication");
  }
  return row as TokenPair;
}

async function jsonResponse(response: Response): Promise<unknown> {
  if (!response.body) throw new ClientError("response", response.status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let text = "";
  let size = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > 8 * 1024 * 1024) throw new ClientError("response", response.status);
      text += decoder.decode(next.value, { stream: true });
    }
    text += decoder.decode();
    return JSON.parse(text);
  } catch {
    throw new ClientError("response", response.status);
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/** One instance per active server profile. No token or network fallback to browser storage. */
export class OrionClient {
  readonly origin: string;
  private readonly fetcher: typeof fetch;
  private refreshFlight: Promise<TokenPair> | null = null;
  private generation = 0;
  private vaultWrites: Promise<void> = Promise.resolve();

  constructor(private readonly options: Options) {
    this.origin = serverOrigin(options.origin);
    if (options.mode === "native" && typeof options.fetch !== "function") {
      throw new ClientError("configuration");
    }
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  dispose(): void {
    this.generation += 1;
  }

  private writeVault(action: () => Promise<void>): Promise<void> {
    const operation = this.vaultWrites.then(action);
    this.vaultWrites = operation.catch(() => {});
    return operation;
  }

  private async save(pair: TokenPair, generation: number): Promise<void> {
    const options = this.options;
    if (options.mode !== "native") throw new ClientError("configuration");
    await this.writeVault(async () => {
      if (generation !== this.generation) throw new ClientError("authentication");
      await options.tokens.set(this.origin, pair);
    });
  }

  private async credentials(): Promise<TokenPair | null> {
    if (this.options.mode === "browser") return null;
    try {
      const value = await this.options.tokens.get(this.origin);
      return value === null ? null : tokenPair(value);
    } catch {
      throw new ClientError("authentication");
    }
  }

  private async forget(): Promise<void> {
    this.generation += 1;
    const options = this.options;
    if (options.mode === "native") {
      try {
        await this.writeVault(() => options.tokens.clear(this.origin));
      } catch {
        throw new ClientError("authentication");
      }
    }
  }

  private async exchange(path: string, body: unknown): Promise<TokenPair> {
    let response: Response;
    try {
      response = await this.fetcher(this.origin + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      // A lost rotation response is ambiguous. Replaying its refresh token revokes the family.
      throw new ClientError("authentication");
    }
    if (!response.ok || response.redirected) {
      await response.body?.cancel().catch(() => {});
      throw new ClientError("authentication", response.status);
    }
    return tokenPair(await jsonResponse(response));
  }

  async enroll(code: string, name: string, platform: "windows" | "linux" | "android" | "ios") {
    if (this.options.mode !== "native") throw new ClientError("configuration");
    await this.forget();
    const generation = this.generation;
    const pair = await this.exchange("/api/auth/native/enroll", { code, name, platform });
    if (generation !== this.generation) throw new ClientError("authentication");
    try {
      await this.save(pair, generation);
    } catch {
      throw new ClientError("authentication");
    }
  }

  private async refresh(previous: TokenPair, generation: number): Promise<TokenPair> {
    if (generation !== this.generation || this.options.mode !== "native") {
      throw new ClientError("authentication");
    }
    if (!this.refreshFlight) {
      this.refreshFlight = (async () => {
        try {
          const current = await this.credentials();
          if (!current || generation !== this.generation) throw new ClientError("authentication");
          if (current.access_token !== previous.access_token) return current;
          const next = await this.exchange("/api/auth/native/refresh", {
            refresh_token: current.refresh_token,
          });
          if (generation !== this.generation) throw new ClientError("authentication");
          await this.save(next, generation);
          return next;
        } catch {
          if (generation === this.generation) await this.forget();
          throw new ClientError("authentication");
        }
      })().finally(() => {
        this.refreshFlight = null;
      });
    }
    return this.refreshFlight;
  }

  async logout(): Promise<void> {
    const pair = await this.credentials();
    await this.forget();
    if (!pair) return;
    try {
      const response = await this.fetcher(this.origin + "/api/auth/native/logout", {
        method: "POST",
        headers: { Authorization: "Bearer " + pair.access_token },
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
      await response.body?.cancel().catch(() => {});
      if (!response.ok || response.redirected)
        throw new ClientError("authentication", response.status);
    } catch {
      throw new ClientError("authentication");
    }
  }

  async request<K extends OperationId>(
    operation: K,
    input: Operations[K]["input"],
    signal?: AbortSignal,
  ): Promise<Operations[K]["output"]> {
    const response = await this.response(operation, input, signal);
    const descriptor = operations[operation];
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new ClientError(
        response.status === 401 ? "authentication" : "response",
        response.status,
      );
    }
    if (descriptor.response === "stream") {
      if (!response.body) throw new ClientError("response", response.status);
      return response.body as Operations[K]["output"];
    }
    if (descriptor.response === "empty") {
      await response.body?.cancel().catch(() => {});
      return undefined as Operations[K]["output"];
    }
    return (await jsonResponse(response)) as Operations[K]["output"];
  }

  /** Raw response adapter retains the same operation authentication and retry policy. */
  async response<K extends OperationId>(
    operation: K,
    input: Operations[K]["input"],
    signal?: AbortSignal,
  ): Promise<Response> {
    const descriptor = operations[operation];
    // Authentication exchange has dedicated methods so raw tokens cannot bypass the vault.
    if (
      ["/api/auth/native/enroll", "/api/auth/native/refresh", "/api/auth/native/logout"].includes(
        descriptor.path,
      )
    )
      throw new ClientError("configuration");
    const values = input as {
      path?: Record<string, unknown>;
      query?: Record<string, unknown>;
      headers?: Record<string, unknown>;
      body?: unknown;
    };
    const path = descriptor.path.replace(/\{([^}]+)\}/g, (_, key: string) => {
      const value = values.path?.[key];
      if (
        typeof value !== "string" ||
        !value ||
        value === "." ||
        value === ".." ||
        /[\\/]/.test(value) ||
        Array.from(value).some(
          (character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
        )
      ) {
        throw new ClientError("configuration");
      }
      return encodeURIComponent(value);
    });
    const url = new URL(this.origin + path);
    for (const [key, value] of Object.entries(values.query ?? {})) {
      if (value === undefined || value === null) continue;
      for (const item of Array.isArray(value) ? value : [value]) {
        url.searchParams.append(key, String(item));
      }
    }
    const headers = new Headers();
    for (const [key, value] of Object.entries(values.headers ?? {})) {
      if (["authorization", "cookie", "origin", "host"].includes(key.toLowerCase())) {
        throw new ClientError("configuration");
      }
      if (!(descriptor.headers as readonly string[]).includes(key.toLowerCase())) {
        throw new ClientError("configuration");
      }
      headers.set(key, String(value));
    }
    let body: BodyInit | undefined;
    if (values.body !== undefined) {
      switch (descriptor.body) {
        case "json":
          headers.set("Content-Type", "application/json");
          body = JSON.stringify(values.body);
          break;
        case "binary":
          if (!(values.body instanceof Blob)) throw new ClientError("configuration");
          headers.set("Content-Type", "application/octet-stream");
          body = values.body;
          break;
        case "form": {
          const form = new FormData();
          for (const [key, value] of Object.entries(values.body as Record<string, unknown>)) {
            if (value instanceof Blob) form.append(key, value);
            else if (value !== undefined && value !== null) form.append(key, String(value));
          }
          body = form;
          break;
        }
        default:
          throw new ClientError("configuration");
      }
    }
    const generation = this.generation;
    let pair = descriptor.auth === "owner" ? await this.credentials() : null;
    if (descriptor.auth === "owner" && this.options.mode === "native" && !pair) {
      throw new ClientError("authentication");
    }
    let refreshed = false;
    let retried = false;
    while (true) {
      if (signal?.aborted) throw new ClientError("cancelled");
      if (generation !== this.generation) throw new ClientError("authentication");
      const attemptHeaders = new Headers(headers);
      if (pair) attemptHeaders.set("Authorization", "Bearer " + pair.access_token);
      let response: Response;
      try {
        response = await this.fetcher(url.toString(), {
          method: descriptor.method,
          headers: attemptHeaders,
          body,
          signal,
          credentials: this.options.mode === "native" ? "omit" : "same-origin",
          redirect: "error",
          cache: "no-store",
        });
      } catch {
        if (signal?.aborted) throw new ClientError("cancelled");
        if (descriptor.idempotentAdmission && !retried) {
          retried = true;
          continue;
        }
        throw new ClientError("network");
      }
      if (signal?.aborted) {
        await response.body?.cancel().catch(() => {});
        throw new ClientError("cancelled");
      }
      if (generation !== this.generation || response.redirected) {
        await response.body?.cancel().catch(() => {});
        throw new ClientError("authentication");
      }
      if (
        response.status === 401 &&
        response.headers.get("X-Orion-Auth-Expired") === "1" &&
        pair &&
        !refreshed
      ) {
        await response.body?.cancel().catch(() => {});
        pair = await this.refresh(pair, generation);
        refreshed = true;
        continue;
      }
      if (signal && response.body) {
        return new Response(
          response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>(), { signal }),
          {
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
          },
        );
      }
      return response;
    }
  }
}
