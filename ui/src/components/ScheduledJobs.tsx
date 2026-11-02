import { useEffect, useState } from "react";
import { serverRequest } from "@/lib/server-profiles";

export function ScheduledJobs({ sessionId }: { sessionId: string }) {
  const [jobs, setJobs] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  const [history, setHistory] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  const [prompt, setPrompt] = useState("");
  const [kind, setKind] = useState<"once" | "recurring">("once");
  const [runAt, setRunAt] = useState("");
  const [cron, setCron] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    setJobs([]);
    setHistory([]);
    setNotice("");
    if (!sessionId) return;
    const controller = new AbortController();
    void serverRequest(
      "list_tasks_api_scheduler_tasks_get",
      { query: { session_id: sessionId } },
      controller.signal,
    )
      .then(setJobs)
      .catch(() => {
        if (!controller.signal.aborted) setNotice("Không thể tải jobs.");
      });
    return () => controller.abort();
  }, [sessionId]);
  async function action(operation: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      await operation();
      setJobs(
        await serverRequest("list_tasks_api_scheduler_tasks_get", {
          query: { session_id: sessionId },
        }),
      );
    } catch {
      setNotice("Thao tác job chưa được xác nhận; kiểm tra lịch và trạng thái trước khi tạo lại.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Scheduled jobs" className="space-y-2">
      <h3>Jobs</h3>
      <p>
        Chọn scope hội thoại ở trên. Scheduler luôn chạy read_only; lịch không cấp quyền shell
        mutation.
      </p>
      {notice && <p role="status">{notice}</p>}
      {sessionId && (
        <>
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              void action(async () => {
                const schedule =
                  kind === "once" ? { run_at: new Date(runAt).toISOString() } : { cron, timezone };
                await serverRequest("create_task_api_scheduler_tasks_post", {
                  body: { session_id: sessionId, prompt, schedule_kind: kind, ...schedule },
                });
                setPrompt("");
              });
            }}
          >
            <label>
              Nội dung job
              <textarea
                className="block w-full rounded border bg-background p-2"
                required
                maxLength={16000}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                disabled={busy}
              />
            </label>
            <label>
              Kiểu lịch
              <select
                className="block rounded border bg-background p-2"
                value={kind}
                onChange={(event) => setKind(event.target.value as typeof kind)}
                disabled={busy}
              >
                <option value="once">Một lần</option>
                <option value="recurring">Lặp lại</option>
              </select>
            </label>
            {kind === "once" ? (
              <label>
                Thời gian theo múi giờ máy
                <input
                  className="block rounded border bg-background p-2"
                  type="datetime-local"
                  required
                  value={runAt}
                  onChange={(event) => setRunAt(event.target.value)}
                  disabled={busy}
                />
              </label>
            ) : (
              <>
                <label>
                  Cron
                  <input
                    className="block rounded border bg-background p-2"
                    required
                    value={cron}
                    maxLength={256}
                    onChange={(event) => setCron(event.target.value)}
                    disabled={busy}
                  />
                </label>
                <label>
                  Múi giờ IANA
                  <input
                    className="block rounded border bg-background p-2"
                    required
                    value={timezone}
                    maxLength={128}
                    onChange={(event) => setTimezone(event.target.value)}
                    disabled={busy}
                  />
                </label>
              </>
            )}
            <button type="submit" className="rounded border px-2 py-1" disabled={busy}>
              Tạo job
            </button>
          </form>
          <ul>
            {jobs.map((job) => {
              const id = typeof job.task_id === "string" ? job.task_id : "";
              if (!id) return null;
              return (
                <li key={id} className="rounded border p-2 space-y-2">
                  <p className="break-all">
                    {id} · {String(job.state ?? job.status ?? "configured")} ·{" "}
                    {String(job.next_run_at ?? "")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {(["pause", "resume", "history", "delete"] as const).map((name) => (
                      <button
                        key={name}
                        type="button"
                        className="rounded border px-2 py-1"
                        disabled={busy}
                        onClick={() => {
                          if (name === "delete" && !window.confirm("Xóa job đã chọn?")) return;
                          void action(async () => {
                            const path = { task_id: id },
                              query = { session_id: sessionId };
                            if (name === "pause")
                              await serverRequest(
                                "pause_task_api_scheduler_tasks__task_id__pause_post",
                                { path, query },
                              );
                            else if (name === "resume")
                              await serverRequest(
                                "resume_task_api_scheduler_tasks__task_id__resume_post",
                                { path, query },
                              );
                            else if (name === "delete")
                              await serverRequest(
                                "delete_task_api_scheduler_tasks__task_id__delete",
                                { path, query },
                              );
                            else
                              setHistory(
                                await serverRequest(
                                  "task_history_api_scheduler_tasks__task_id__history_get",
                                  { path, query: { ...query, limit: 10 } },
                                ),
                              );
                          });
                        }}
                      >
                        {name} job
                      </button>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
          {history.length > 0 && (
            <ul aria-label="Job run history">
              {history.map((row, index) => (
                <li key={String(row.run_id ?? index)}>
                  {String(row.status ?? row.state ?? "unknown")} · {String(row.request_id ?? "")}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
