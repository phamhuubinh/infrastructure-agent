import { useEffect, useState } from "react";
import { serverRequest } from "@/lib/server-profiles";
import type { Schemas } from "@/lib/sdk/generated";
import { ScheduledJobs } from "./ScheduledJobs";

export function RuntimeResources() {
  const [sessions, setSessions] = useState<ReadonlyArray<Schemas["SessionSummaryView"]>>([]);
  const [sessionId, setSessionId] = useState("");
  const [skills, setSkills] = useState<ReadonlyArray<Schemas["SkillDescriptor"]>>([]);
  const [servers, setServers] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  const [doctor, setDoctor] = useState<Schemas["DoctorView"] | null>(null);
  const [code, setCode] = useState<Schemas["NativeEnrollmentCode"] | null>(null);
  const [nativeSessions, setNativeSessions] = useState<ReadonlyArray<Schemas["NativeSessionView"]>>(
    [],
  );
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      serverRequest("list_sessions_api_sessions_get", {}, controller.signal),
      serverRequest("servers_api_mcp_servers_get", {}, controller.signal),
      serverRequest("doctor_api_doctor_get", {}, controller.signal),
      serverRequest("sessions_api_auth_native_sessions_get", {}, controller.signal),
    ])
      .then(([loadedSessions, loadedServers, status, families]) => {
        setSessions(loadedSessions);
        setServers(loadedServers);
        setDoctor(status);
        setNativeSessions(families);
      })
      .catch(() => {
        if (!controller.signal.aborted) setNotice("Không thể tải cấu hình runtime.");
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setSkills([]);
    if (!sessionId) return;
    const controller = new AbortController();
    void serverRequest(
      "catalog_api_sessions__session_id__skills_get",
      { path: { session_id: sessionId } },
      controller.signal,
    )
      .then(setSkills)
      .catch(() => {
        if (!controller.signal.aborted) setNotice("Không thể tải skill trong scope này.");
      });
    return () => controller.abort();
  }, [sessionId]);
  useEffect(() => {
    if (!code) return;
    const timer = setTimeout(() => setCode(null), Math.max(0, code.expires_at * 1000 - Date.now()));
    return () => clearTimeout(timer);
  }, [code]);
  async function action(operation: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      await operation();
    } catch {
      setNotice("Thao tác chưa được xác nhận. Kiểm tra trạng thái trước khi thử lại.");
    } finally {
      setBusy(false);
    }
  }
  async function reloadSkills() {
    setSkills(
      await serverRequest("catalog_api_sessions__session_id__skills_get", {
        path: { session_id: sessionId },
      }),
    );
  }
  return (
    <section aria-label="Runtime resources" className="space-y-4 rounded-lg border p-4">
      <h2 className="font-semibold">Runtime, Skills và MCP</h2>
      {doctor && (
        <p>
          Quan sát cấu hình · model{" "}
          {doctor.model_profile_configured ? "đã cấu hình" : "chưa cấu hình"} · MCP{" "}
          {doctor.mcp_connected}/{doctor.mcp_configured} · request đang chạy{" "}
          {doctor.active_requests}. Đây không phải kiểm tra live.
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <section aria-label="Native enrollment" className="space-y-2">
        <h3>Kết nối ứng dụng native</h3>
        <button
          type="button"
          disabled={busy}
          className="rounded border px-2 py-1"
          onClick={() =>
            void action(async () =>
              setCode(
                await serverRequest("create_enrollment_api_auth_native_enrollment_codes_post", {}),
              ),
            )
          }
        >
          Tạo mã kết nối một lần
        </button>
        {code && (
          <div>
            <label>
              Mã dùng một lần
              <input
                type="password"
                readOnly
                value={code.code}
                autoComplete="off"
                className="block w-full rounded border bg-background p-2"
              />
            </label>
            <p>Hết hạn: {new Date(code.expires_at * 1000).toLocaleString()}</p>
            <button
              type="button"
              onClick={() =>
                void navigator.clipboard
                  .writeText(code.code)
                  .catch(() => setNotice("Không thể copy mã trong môi trường này."))
              }
            >
              Copy mã
            </button>
            <button type="button" onClick={() => setCode(null)}>
              Ẩn mã
            </button>
          </div>
        )}
      </section>
      <section aria-label="Native sessions" className="space-y-2">
        <h3>Ứng dụng đã kết nối</h3>
        <ul>
          {nativeSessions.map((session) => (
            <li key={session.session_id} className="flex flex-wrap gap-2 items-center">
              <span>
                {session.name} · {session.platform} ·{" "}
                {session.revoked_at
                  ? "đã thu hồi"
                  : "hết hạn " + new Date(session.expires_at * 1000).toLocaleString()}
              </span>
              {!session.revoked_at && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await serverRequest(
                        "revoke_api_auth_native_sessions__native_session_id__revoke_post",
                        { path: { native_session_id: session.session_id } },
                      );
                      setNativeSessions(
                        await serverRequest("sessions_api_auth_native_sessions_get", {}),
                      );
                    })
                  }
                >
                  Thu hồi {session.name}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="MCP servers" className="space-y-2">
        <h3>MCP</h3>
        {!servers.length && <p>Không có MCP server trong cấu hình chủ server.</p>}
        {servers.map((server) => {
          const id = typeof server.server_id === "string" ? server.server_id : "";
          if (!id) return null;
          return (
            <div key={id} className="flex flex-wrap items-center gap-2">
              <span>
                {id} · {String(server.state ?? "unknown")}
              </span>
              {(["connect", "disconnect", "test"] as const).map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={busy}
                  className="rounded border px-2 py-1"
                  onClick={() =>
                    void action(async () => {
                      const path = { server_id: id };
                      if (name === "connect")
                        await serverRequest("connect_api_mcp_servers__server_id__connect_post", {
                          path,
                        });
                      else if (name === "disconnect")
                        await serverRequest(
                          "disconnect_api_mcp_servers__server_id__disconnect_post",
                          { path },
                        );
                      else
                        await serverRequest("test_api_mcp_servers__server_id__test_post", { path });
                      setServers(await serverRequest("servers_api_mcp_servers_get", {}));
                    })
                  }
                >
                  {name}
                </button>
              ))}
            </div>
          );
        })}
      </section>
      <label>
        Scope hội thoại
        <select
          disabled={busy}
          className="block w-full rounded border bg-background p-2"
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
      <ScheduledJobs key={sessionId} sessionId={sessionId} />
      <section aria-label="Product skills" className="space-y-2">
        <h3>Skills</h3>
        <p>
          Skill là hướng dẫn, không cấp quyền thực thi. Chỉ gói product ZIP có SKILL.md ở root;
          không nhận đường dẫn server hay development skill.
        </p>
        {sessionId && (
          <label>
            Cài hoặc cập nhật product skill (.zip)
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (!file) return;
                if (file.size > 2097152) {
                  setNotice("Gói ZIP vượt giới hạn 2 MiB.");
                  return;
                }
                const project = sessions.find(
                  (session) => session.session_id === sessionId,
                )?.project_id;
                void action(async () => {
                  await serverRequest("install_package_api_skills_packages_post", {
                    query: { source: project ? "project" : "user", project_id: project },
                    body: file,
                  });
                  await reloadSkills();
                });
              }}
            />
          </label>
        )}
        <ul className="space-y-2">
          {skills.map((skill) => (
            <li key={`${skill.source}:${skill.name}`} className="flex flex-wrap items-center gap-2">
              <span>
                {skill.name}@{skill.version} · {skill.source}
              </span>
              <label>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={skill.enabled ?? true}
                  onChange={(event) => {
                    const enabled = event.target.checked;
                    void action(async () => {
                      await serverRequest("preference_api_skills__name__patch", {
                        path: { name: skill.name },
                        body: { source: skill.source, project_id: skill.project_id, enabled },
                      });
                      await reloadSkills();
                    });
                  }}
                />
                Bật {skill.name}
              </label>
              {skill.source !== "bundled" && (
                <button
                  type="button"
                  disabled={busy}
                  className="rounded border px-2 py-1"
                  onClick={() =>
                    void action(async () => {
                      await serverRequest("remove_api_skills__name__delete", {
                        path: { name: skill.name },
                        query: {
                          source: skill.source as "user" | "project",
                          project_id: skill.project_id,
                        },
                      });
                      await reloadSkills();
                    })
                  }
                >
                  Gỡ {skill.name}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
