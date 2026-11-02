import { ClientError } from "./client";

export type ServerEvent = { id: string; data: string; event: string };

/** Incremental SSE decoding; callers persist the event UUID and reconnect observation only. */
export async function* serverEvents(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let pending = "";
  let id = "";
  let event = "message";
  let data: string[] = [];
  let eventSize = 0;
  const line = (value: string): ServerEvent | null => {
    if (value === "") {
      const result = data.length ? { id, event, data: data.join("\n") } : null;
      data = [];
      event = "message";
      eventSize = 0;
      return result;
    }
    eventSize += value.length;
    if (eventSize > 1024 * 1024) throw new ClientError("response");
    if (value.startsWith(":")) return null;
    const colon = value.indexOf(":");
    const key = colon < 0 ? value : value.slice(0, colon);
    let content = colon < 0 ? "" : value.slice(colon + 1);
    if (content.startsWith(" ")) content = content.slice(1);
    if (key === "id" && !content.includes("\0")) id = content;
    if (key === "event") event = content;
    if (key === "data") data.push(content);
    return null;
  };
  try {
    while (true) {
      const next = await reader.read();
      pending += next.done ? decoder.decode() : decoder.decode(next.value, { stream: true });
      // A CR at the end may be the first half of CRLF; retain it until the next chunk.
      while (true) {
        const index = pending.search(/[\r\n]/);
        if (index < 0 || (!next.done && index === pending.length - 1 && pending[index] === "\r")) {
          break;
        }
        const skip = pending[index] === "\r" && pending[index + 1] === "\n" ? 2 : 1;
        const result = line(pending.slice(0, index));
        pending = pending.slice(index + skip);
        if (result) yield result;
      }
      if (pending.length > 1024 * 1024) throw new ClientError("response");
      // EOF without a blank delimiter is an incomplete event, not a completion signal.
      if (next.done) return;
    }
  } catch {
    throw new ClientError("response");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
