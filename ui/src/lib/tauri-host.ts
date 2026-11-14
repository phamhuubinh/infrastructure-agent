import { newUuid } from "./uuid";
import { invoke } from "@tauri-apps/api/core";
import { installNativeHost } from "./server-profiles";
import type { SecureTokenStore } from "./sdk/client";

type HostInfo = {
  platform?: "windows" | "android" | "ios";
  managedOrigin: string | null;
  hostMode?: boolean;
  hostOrigin?: string | null;
  managedError?: string | null;
};
type ResponseHead = { status: number; headers: [string, string][] };

export async function installTauriHost() {
  const {
    platform = "windows",
    managedOrigin,
    managedError,
    hostMode,
    hostOrigin,
  } = await invoke<HostInfo>("orion_host");
  if (!["windows", "android", "ios"].includes(platform)) throw new Error("Invalid Orion host");
  const tokens: SecureTokenStore = {
    get: (origin) => invoke("orion_vault_get", { origin }),
    set: (origin, pair) => invoke("orion_vault_set", { origin, pair }),
    clear: (origin) => invoke("orion_vault_clear", { origin }),
  };
  installNativeHost({
    platform,
    tokens,
    fetch: nativeFetch(false, platform !== "windows"),
    hostOrigin: hostOrigin ?? undefined,
    stopHost: hostMode ? () => invoke<void>("orion_stop_host") : undefined,
    managedError: managedError ?? undefined,
    managedBackend: managedOrigin ? { origin: managedOrigin, fetch: nativeFetch(true) } : undefined,
  });
}

function mobileBody(body: Uint8Array): string {
  const chunks: string[] = [];
  for (let offset = 0; offset < body.length; offset += 16384) {
    chunks.push(String.fromCharCode(...body.subarray(offset, offset + 16384)));
  }
  return btoa(chunks.join(""));
}

function nativeFetch(managed: boolean, mobile = false): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init);
    const { signal, url, method, headers } = request;
    const body = new Uint8Array(await request.arrayBuffer());
    signal.throwIfAborted();
    const id = newUuid();
    let closed = false;
    const close = () => {
      if (closed) return Promise.resolve();
      closed = true;
      signal.removeEventListener("abort", abort);
      return invoke<void>("orion_close", { id }).catch(() => {});
    };
    const abort = () => void close();

    try {
      await invoke("orion_prepare", {
        id,
        request: { managed, origin: new URL(url).origin, url, method, headers: [...headers] },
      });
      signal.addEventListener("abort", abort, { once: true });
      signal.throwIfAborted();
      const head = mobile
        ? await invoke<ResponseHead>("orion_start_mobile", { id, body: mobileBody(body) })
        : await invoke<ResponseHead>("orion_start", body, { headers: { "x-orion-request": id } });
      signal.throwIfAborted();
      if (head.status === 204 || head.status === 205) {
        await close();
        return new Response(null, head);
      }
      const stream = new ReadableStream<Uint8Array>({
        async pull(controller) {
          try {
            signal.throwIfAborted();
            const bytes = mobile
              ? Uint8Array.from(atob(await invoke<string>("orion_read_mobile", { id })), (byte) =>
                  byte.charCodeAt(0),
                )
              : new Uint8Array(await invoke<ArrayBuffer>("orion_read", { id }));
            signal.throwIfAborted();
            if (bytes.byteLength > 0) {
              controller.enqueue(bytes);
            } else {
              controller.close();
              await close();
            }
          } catch (error) {
            controller.error(error);
            await close();
          }
        },
        cancel: close,
      });
      return new Response(stream, head);
    } catch (error) {
      await close();
      throw error;
    }
  };
}
