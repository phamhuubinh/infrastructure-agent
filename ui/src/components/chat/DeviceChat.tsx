import { useCallback, useEffect, useRef, useState } from "react";

import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";
import { AssistantMessage, UserMessage } from "@/components/chat/Message";
import { Button } from "@/components/ui/button";
import { apiFetch, apiJson, type MutationMode } from "@/lib/api";
import { type TimelineItem } from "@/lib/chat-store";
import { parseSseEvents } from "@/lib/chat-stream";

type Session = { session_id: string; endpoint_id: string; mutation_mode: MutationMode };
type Pending = { request: string; call: string; tool: string; summary: Record<string, string> };

// State belongs only to this endpoint workspace, never the ordinary Chat provider/sidebar.
export function DeviceChat({ endpointId }: { endpointId: string }) {
  const [session, setSession] = useState<Session | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const controller = useRef<AbortController | null>(null);
  const requestId = useRef<string | null>(null);

  const refresh = useCallback(async (sessionId: string) => {
    setTimeline(await apiJson<TimelineItem[]>(`/api/sessions/${sessionId}/timeline`));
  }, []);

  useEffect(() => {
    let disposed = false;
    void apiJson<Session>(`/api/endpoints/${endpointId}/chat`, { method: "POST" })
      .then(async (value) => {
        if (disposed) return;
        setSession(value);
        await refresh(value.session_id);
      })
      .catch((reason: unknown) => {
        if (!disposed)
          setError(reason instanceof Error ? reason.message : "Device Chat unavailable.");
      });
    return () => {
      disposed = true;
      controller.current?.abort();
      if (requestId.current) {
        void apiFetch(`/api/requests/${requestId.current}/cancel`, {
          method: "POST",
          keepalive: true,
        }).catch(() => {});
      }
    };
  }, [endpointId, refresh]);

  async function send() {
    if (!session || !content.trim() || controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    const message = content.trim();
    setContent("");
    try {
      const response = await apiFetch(`/api/sessions/${session.session_id}/messages/stream`, {
        method: "POST",
        body: JSON.stringify({ content: message }),
        signal: abort.signal,
      });
      if (!response.ok || !response.body) throw new Error("Device Chat request unavailable.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        if (buffer.length > 1500000) throw new Error("Device Chat event exceeds limit.");
        const parsed = parseSseEvents(buffer);
        buffer = parsed.remainder;
        for (const event of parsed.events) {
          if (event.type === "request.accepted")
            requestId.current = String(event.payload.request_id);
          if (event.type === "tool.authorization_required" && requestId.current) {
            setPending({
              request: requestId.current,
              call: String(event.payload.call_id),
              tool: String(event.payload.tool_name),
              summary: event.payload.summary as Record<string, string>,
            });
          }
          if (event.type === "request.failed")
            setError(String(event.payload.message ?? "Request failed."));
          if (event.type === "assistant.message" || event.type === "request.accepted")
            await refresh(session.session_id);
        }
        if (done) break;
      }
    } catch (reason) {
      if (!abort.signal.aborted)
        setError(reason instanceof Error ? reason.message : "Request failed.");
    } finally {
      controller.current = null;
      requestId.current = null;
      setPending(null);
      setBusy(false);
      await refresh(session.session_id).catch(() => {});
    }
  }

  async function authorize(decision: "allow" | "deny") {
    if (!session || !pending) return;
    try {
      await apiJson(
        `/api/sessions/${session.session_id}/requests/${pending.request}/tool-authorizations/${pending.call}`,
        {
          method: "POST",
          body: JSON.stringify({ decision }),
        },
      );
      setPending(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authorization failed.");
    }
  }

  return (
    <section className="space-y-3" aria-label="Device Chat">
      <p>Device Chat · Lịch sử riêng của thiết bị · Không có Project hoặc tài liệu đính kèm.</p>
      <label>
        Quyền sửa Device Chat{" "}
        <select
          aria-label="Quyền sửa Device Chat"
          value={session?.mutation_mode ?? "read_only"}
          disabled={!session || busy}
          onChange={(event) => {
            const mode = event.target.value as MutationMode;
            if (
              mode === "auto" &&
              !window.confirm("Cho phép Device Chat tự động thực hiện thao tác thay đổi?")
            )
              return;
            void apiJson<Session>(`/api/sessions/${session!.session_id}/mutation-mode`, {
              method: "PATCH",
              body: JSON.stringify({ mutation_mode: mode }),
            })
              .then((value) =>
                setSession(
                  (current) => current && { ...current, mutation_mode: value.mutation_mode },
                ),
              )
              .catch((reason: unknown) =>
                setError(reason instanceof Error ? reason.message : "Mode update failed."),
              );
          }}
        >
          <option value="read_only">Chỉ đọc</option>
          <option value="confirm">Hỏi trước khi sửa</option>
          <option value="auto">Tự động sửa</option>
        </select>
      </label>
      {timeline
        .filter((item) => item.kind === "user_message" || item.kind === "assistant_message")
        .map((item) => {
          const text = String(item.payload.content ?? "");
          return item.kind === "user_message" ? (
            <UserMessage key={item.item_id}>{text}</UserMessage>
          ) : (
            <AssistantMessage key={item.item_id}>
              <AssistantMarkdown>{text}</AssistantMarkdown>
            </AssistantMessage>
          );
        })}
      {pending && (
        <div role="alertdialog" aria-label="Xác nhận thao tác Device Chat">
          <p>
            {pending.tool} · {pending.summary?.label}
          </p>
          <Button onClick={() => void authorize("deny")}>Từ chối</Button>
          <Button onClick={() => void authorize("allow")}>Cho phép</Button>
        </div>
      )}
      <textarea
        aria-label="Nhắn Device Chat"
        value={content}
        maxLength={16000}
        onChange={(event) => setContent(event.target.value)}
      />
      <Button disabled={!session || busy || !content.trim()} onClick={() => void send()}>
        Gửi Device Chat
      </Button>
      <Button
        disabled={!busy}
        onClick={() => {
          if (requestId.current)
            void apiFetch(`/api/requests/${requestId.current}/cancel`, { method: "POST" }).catch(
              () => {},
            );
          controller.current?.abort();
        }}
      >
        Dừng trả lời
      </Button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
