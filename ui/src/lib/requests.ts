import { newUuid } from "./uuid";
import { serverEvents } from "./sdk/events";
import type { Schemas } from "./sdk/generated";
import {
  activeServer,
  serverRequest,
  serverContext,
  SERVER_CHANGED_EVENT,
} from "./server-profiles";

export type RequestIntent = Readonly<{
  origin: string;
  sessionId: string;
  content: string;
  clientId: string;
  context: AbortSignal;
}>;
type EventRecord = Schemas["RequestEventRecord"];
type Pending = { intent: RequestIntent; requestId?: string; cursor?: string };
const pending = new Map<string, Pending>();
const key = (intent: RequestIntent) => JSON.stringify([intent.origin, intent.sessionId]);
function forget(intent: RequestIntent) {
  if (pending.get(key(intent))?.intent.clientId === intent.clientId) pending.delete(key(intent));
}
window.addEventListener(SERVER_CHANGED_EVENT, () => pending.clear());
window.addEventListener("orion-auth-expired", () => pending.clear());

export function pendingIntent(sessionId: string): RequestIntent | null {
  return pending.get(JSON.stringify([activeServer().origin, sessionId]))?.intent ?? null;
}

export function pendingObservation(sessionId: string): RequestIntent | null {
  const saved = pending.get(JSON.stringify([activeServer().origin, sessionId]));
  return saved?.requestId ? saved.intent : null;
}

export function requestIntent(sessionId: string, content: string): RequestIntent {
  const intent = Object.freeze({
    origin: activeServer().origin,
    sessionId,
    content,
    clientId: newUuid(),
    context: serverContext(),
  });
  const previous = pending.get(key(intent));
  if (previous) {
    if (previous.intent.content !== content)
      throw new Error("Yêu cầu trước chưa xác minh. Tiếp tục quan sát hoặc dừng yêu cầu đó trước.");
    return previous.intent;
  }
  if (pending.size >= 64) throw new Error("Có quá nhiều yêu cầu chưa xác minh.");
  pending.set(key(intent), { intent });
  return intent;
}

function sameServer(intent: RequestIntent) {
  if (activeServer().origin !== intent.origin || serverContext() !== intent.context)
    throw new Error("Server đã thay đổi.");
}

export async function cancelIntent(
  intent: RequestIntent,
): Promise<Schemas["RequestView"]["status"]> {
  sameServer(intent);
  let status = await serverRequest(
    "cancel_admission_api_sessions__session_id__request_cancellations_post",
    {
      path: { session_id: intent.sessionId },
      body: { content: intent.content, client_request_id: intent.clientId },
    },
  );
  const deadline = Date.now() + 30000;
  while (["queued", "running"].includes(status.status)) {
    if (Date.now() >= deadline) throw new Error("Chưa xác minh yêu cầu đã dừng.");
    await new Promise<void>((resolve) => setTimeout(resolve, 100));
    sameServer(intent);
    status = await serverRequest("get_request_api_requests__request_id__get", {
      path: { request_id: status.request_id },
    });
  }
  forget(intent);
  return status.status;
}

/** Admit once. Every reconnect after that observes the same request/event UUID. */
export async function runIntent(
  intent: RequestIntent,
  onAdmitted: (requestId: string) => void,
  onEvent: (event: EventRecord) => void | Promise<void>,
  signal: AbortSignal,
): Promise<void> {
  sameServer(intent);
  const saved = pending.get(key(intent)) ?? { intent };
  if (saved.intent.clientId !== intent.clientId) throw new Error("Yêu cầu hội thoại đã thay đổi.");
  pending.set(key(intent), saved);
  const admitted = saved.requestId
    ? { request_id: saved.requestId }
    : await serverRequest(
        "admit_api_sessions__session_id__requests_post",
        {
          path: { session_id: intent.sessionId },
          body: { content: intent.content, client_request_id: intent.clientId },
        },
        signal,
      );
  saved.requestId = admitted.request_id;
  onAdmitted(admitted.request_id);
  let cursor = saved.cursor;
  let terminal = false;
  const accept = async (event: EventRecord) => {
    if (
      typeof event.event_id !== "string" ||
      typeof event.type !== "string" ||
      typeof event.created_at !== "string" ||
      !event.payload ||
      typeof event.payload !== "object"
    ) {
      throw new Error("Sự kiện Orion không hợp lệ.");
    }
    if (cursor === event.event_id) return;
    await onEvent(event);
    cursor = event.event_id;
    saved.cursor = cursor;
    terminal = [
      "request.completed",
      "request.incomplete",
      "request.failed",
      "request.cancelled",
    ].includes(event.type);
  };
  for (let attempt = 0; attempt < 4; attempt++) {
    sameServer(intent);
    if (signal.aborted) throw new DOMException("Observation cancelled", "AbortError");
    try {
      const stream = await serverRequest(
        "stream_api_requests__request_id__stream_get",
        {
          path: { request_id: admitted.request_id },
          query: { after: cursor },
        },
        signal,
      );
      for await (const event of serverEvents(stream)) {
        if (signal.aborted) throw new DOMException("Observation cancelled", "AbortError");
        const record = JSON.parse(event.data) as EventRecord;
        if (record.event_id !== event.id) throw new Error("Cursor Orion không hợp lệ.");
        await accept(record);
      }
      if (terminal) {
        forget(intent);
        return;
      }
    } catch (error) {
      if (signal.aborted) throw new DOMException("Observation cancelled", "AbortError");
      if (attempt === 3) throw error;
    }
    // Reconcile a lost terminal event from the durable log. This is GET-only;
    // a disconnect never re-enters admission or the model/tool loop.
    let more = true;
    while (more) {
      sameServer(intent);
      let page;
      try {
        page = await serverRequest(
          "events_api_requests__request_id__event_page_get",
          {
            path: { request_id: admitted.request_id },
            query: { after: cursor, limit: 64 },
          },
          signal,
        );
      } catch (error) {
        if (signal.aborted || attempt === 3) throw error;
        await new Promise<void>((resolve) => setTimeout(resolve, 500));
        break;
      }
      for (const event of page.events) await accept(event);
      more = page.has_more;
      if (!more && !["queued", "running"].includes(page.status)) {
        forget(intent);
        return;
      }
    }
  }
  throw new Error("Mất kết nối quan sát. Yêu cầu vẫn có mã riêng; đừng gửi lại cùng thao tác.");
}
