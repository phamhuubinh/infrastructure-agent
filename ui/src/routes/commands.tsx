import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { serverRequest } from "@/lib/server-profiles";
import type { Schemas } from "@/lib/sdk/generated";

export const Route = createFileRoute("/commands")({ component: CommandsPage });

export function CommandsPage() {
  const [sessions, setSessions] = useState<ReadonlyArray<Schemas["SessionSummaryView"]>>([]);
  const [sessionId, setSessionId] = useState("");
  const [commands, setCommands] = useState<ReadonlyArray<Schemas["CommandPage"]>>([]);
  const [selected, setSelected] = useState<Schemas["CommandPage"] | null>(null);
  const [output, setOutput] = useState({ stdout: "", stderr: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void serverRequest("list_sessions_api_sessions_get", {}, controller.signal)
      .then(setSessions)
      .catch(() => {
        if (!controller.signal.aborted) setError("Không thể tải hội thoại.");
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setSelected(null);
    setCommands([]);
    setOutput({ stdout: "", stderr: "" });
    if (!sessionId) return;
    const controller = new AbortController();
    void serverRequest(
      "list_commands_api_sessions__session_id__commands_get",
      { path: { session_id: sessionId } },
      controller.signal,
    )
      .then(setCommands)
      .catch(() => {
        if (!controller.signal.aborted) setError("Không thể tải command metadata.");
      });
    return () => controller.abort();
  }, [sessionId]);
  async function inspect(command: Schemas["CommandPage"], cancel = false) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const path = { session_id: sessionId, command_id: command.command_id };
      const page = cancel
        ? await serverRequest(
            "cancel_api_sessions__session_id__commands__command_id__cancel_post",
            { path },
          )
        : await serverRequest("status_api_sessions__session_id__commands__command_id__get", {
            path,
            query: {
              stdout_offset:
                selected?.command_id === command.command_id
                  ? (selected.next_stdout_offset ?? 0)
                  : 0,
              stderr_offset:
                selected?.command_id === command.command_id
                  ? (selected.next_stderr_offset ?? 0)
                  : 0,
            },
          });
      setSelected(page);
      if (cancel) setOutput({ stdout: page.stdout ?? "", stderr: page.stderr ?? "" });
      else
        setOutput((previous) => ({
          stdout: (
            (selected?.command_id === command.command_id ? previous.stdout : "") +
            (page.stdout ?? "")
          ).slice(-262144),
          stderr: (
            (selected?.command_id === command.command_id ? previous.stderr : "") +
            (page.stderr ?? "")
          ).slice(-262144),
        }));
      setCommands((previous) =>
        previous.map((item) => (item.command_id === page.command_id ? page : item)),
      );
    } catch {
      setError("Không thể xác minh trạng thái command. Không chạy lại lệnh tự động.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="flex-1 min-w-0 overflow-y-auto p-5 space-y-4">
      <h1 className="text-2xl font-semibold">Commands</h1>
      <p>
        Chạy lệnh qua Chat hoặc Device Chat với quyền và xác nhận của hội thoại. Trang này quan sát
        handle đã tạo và yêu cầu dừng; không chạy lại lệnh khi mất kết nối.
      </p>
      <label>
        Hội thoại
        <select
          disabled={busy}
          className="block max-w-full rounded border bg-background p-2"
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
        >
          <option value="">Chọn hội thoại</option>
          {sessions.map((session) => (
            <option key={session.session_id} value={session.session_id}>
              {session.title}
            </option>
          ))}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      <ul className="space-y-2">
        {commands.map((command) => (
          <li
            key={command.command_id}
            className="rounded border p-3 flex flex-wrap gap-2 items-center"
          >
            <span className="break-all">
              {command.target_ref} · {command.shell} · {command.state}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => void inspect(command)}
              className="rounded border px-2 py-1"
            >
              Xem output
            </button>
            {["created", "running", "outcome_unknown"].includes(command.state) && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void inspect(command, true)}
                className="rounded border px-2 py-1"
              >
                Dừng command
              </button>
            )}
          </li>
        ))}
      </ul>
      {sessionId && !commands.length && (
        <p>Chưa có command trong trang metadata đầu tiên của hội thoại.</p>
      )}
      {selected && (
        <section aria-label="Command observation" className="space-y-2">
          <h2 className="font-semibold">
            {selected.state} · exit {selected.exit_code ?? "chưa xác định"}
          </h2>
          {selected.state === "outcome_unknown" && (
            <p role="alert">
              Chưa xác định kết quả. Không coi partial output là thành công và không tự chạy lại.
            </p>
          )}
          {!selected.output_available && (
            <p>Output transient không còn sẵn; metadata không lưu raw output.</p>
          )}
          <p>
            Hiển thị tối đa 256 Ki ký tự cuối mỗi stream. Server báo omitted bytes:{" "}
            {selected.omitted_output_bytes ?? 0}.
          </p>
          <h3>stdout</h3>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded border p-3">
            {output.stdout}
          </pre>
          <h3>stderr</h3>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded border p-3">
            {output.stderr}
          </pre>
        </section>
      )}
    </main>
  );
}
