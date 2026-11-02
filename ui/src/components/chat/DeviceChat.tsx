import { useCallback, useEffect, useRef, useState } from "react";

import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";
import { CommandApprovalReview } from "@/components/chat/CommandApprovalReview";
import { AssistantMessage, UserMessage } from "@/components/chat/Message";
import { Button } from "@/components/ui/button";
import { apiFetch, apiJson, type MutationMode } from "@/lib/api";
import { type TimelineItem } from "@/lib/chat-store";
import {
  runIntent,
  cancelIntent,
  requestIntent,
  pendingIntent,
  type RequestIntent,
} from "@/lib/requests";
import { serverContext } from "@/lib/server-profiles";

type Session = { session_id: string; endpoint_id: string; mutation_mode: MutationMode };
type Pending = { request: string; call: string; tool: string; summary: Record<string, string> };

// State belongs only to this endpoint workspace, never the ordinary Chat provider/sidebar.
export function DeviceChat({ endpointId }: { endpointId: string }) {
  const context = useRef(serverContext()).current;
  const [session, setSession] = useState<Session | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const controller = useRef<AbortController | null>(null);
  const requestId = useRef<string | null>(null);
  const intent = useRef<RequestIntent | null>(null);

  const refresh = useCallback(
    async (sessionId: string) => {
      if (context !== serverContext()) return;
      setTimeline(await apiJson<TimelineItem[]>(`/api/sessions/${sessionId}/timeline`));
    },
    [context],
  );

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
      if (intent.current) void cancelIntent(intent.current).catch(() => {});
    };
  }, [endpointId, refresh]);

  async function send(resume = false) {
    const previous = session ? pendingIntent(session.session_id) : null;
    if (!session || (!content.trim() && !(resume && previous)) || controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    const message = resume && previous ? previous.content : content.trim();
    setContent("");
    try {
      intent.current = resume && previous ? previous : requestIntent(session.session_id, message);
      await runIntent(
        intent.current,
        (identity) => {
          requestId.current = identity;
        },
        async (event) => {
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
        },
        abort.signal,
      );
    } catch (reason) {
      if (!abort.signal.aborted)
        setError(reason instanceof Error ? reason.message : "Request failed.");
    } finally {
      controller.current = null;
      requestId.current = null;
      intent.current = null;
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
          headers: { "Content-Type": "application/json" },
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
              headers: { "Content-Type": "application/json" },
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
          {pending.tool.startsWith("system.command.") && session ? (
            <CommandApprovalReview
              key={`${session.session_id}:${pending.request}:${pending.call}`}
              sessionId={session.session_id}
              requestId={pending.request}
              callId={pending.call}
              toolName={pending.tool}
              onResolved={() => setPending(null)}
            />
          ) : (
            <>
              <Button onClick={() => void authorize("deny")}>Từ chối</Button>
              <Button onClick={() => void authorize("allow")}>Cho phép</Button>
            </>
          )}
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
          const active = controller.current;
          if (intent.current) {
            void cancelIntent(intent.current)
              .then((status) => {
                if (status === "cancelled") active?.abort();
              })
              .catch(() => {
                setError(
                  "Chưa xác nhận server đã dừng yêu cầu. Kiểm tra trạng thái trước khi gửi lại.",
                );
              });
          }
        }}
      >
        Dừng trả lời
      </Button>
      {error && <p role="alert">{error}</p>}
      {session && pendingIntent(session.session_id) && !busy && (
        <>
          <Button onClick={() => void send(true)}>Tiếp tục quan sát</Button>
          <Button
            onClick={() => {
              const previous = pendingIntent(session.session_id);
              if (previous)
                void cancelIntent(previous)
                  .then(() => setError("Yêu cầu đã kết thúc."))
                  .catch(() => setError("Chưa xác minh yêu cầu đã dừng."));
            }}
          >
            Dừng yêu cầu chưa xác minh
          </Button>
        </>
      )}
    </section>
  );
}
