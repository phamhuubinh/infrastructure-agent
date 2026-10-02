import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { DeviceChat } from "@/components/chat/DeviceChat";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, apiJson } from "@/lib/api";

export const Route = createFileRoute("/endpoints")({ component: EndpointsPage });

type Endpoint = {
  endpoint_id: string;
  name: string;
  platform: string | null;
  online: boolean;
  revoked_at: number | null;
  capabilities: string[];
  temporary?: boolean;
  worker_version?: string;
  architecture?: string;
  os_release?: string;
  last_seen?: number;
  system_summary?: { cpu_count?: number; memory_total?: number; memory_available?: number };
  geometry?: Array<{ width: number; height: number }>;
};
type Frame = {
  image_b64: string;
  width: number;
  height: number;
  geometry: { width: number; height: number };
};
type Session = { session_id: string; control_available: boolean };
type Artifacts = {
  available: boolean;
  version: string;
  reason?: string;
  artifacts: Array<{ filename: string; platform: string; sha256: string; url: string }>;
};

export function EndpointsPage() {
  const [devices, setDevices] = useState<Endpoint[]>([]);
  const [artifacts, setArtifacts] = useState<Artifacts | null>(null);
  const [tab, setTab] = useState("Chat");
  const [expires, setExpires] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [selected, setSelected] = useState<Endpoint | null>(null);
  const [token, setToken] = useState("");
  const [label, setLabel] = useState("");
  const [path, setPath] = useState("");
  const [monitor, setMonitor] = useState(1);
  const [overwrite, setOverwrite] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [control, setControl] = useState(false);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const inputPending = useRef(false);
  const sessionRef = useRef<{ endpoint: string; session: string } | null>(null);
  const prefix = selected ? `/api/endpoints/${selected.endpoint_id}` : "";

  const load = useCallback(async () => {
    try {
      const rows = await apiJson<Endpoint[]>("/api/endpoints");
      setDevices(rows);
      setSelected((current) =>
        current ? (rows.find((row) => row.endpoint_id === current.endpoint_id) ?? null) : null,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tải thiết bị.");
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(interval);
  }, [load]);
  useEffect(() => {
    void apiJson<Artifacts>("/api/endpoints/artifacts")
      .then(setArtifacts)
      .catch(() => setArtifacts(null));
  }, []);
  useEffect(() => {
    const update = () => {
      const seconds = Math.max(0, Math.ceil((expires * 1000 - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) setToken("");
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [expires]);

  useEffect(
    () => () => {
      abort.current?.abort();
      const current = sessionRef.current;
      if (current) {
        void apiFetch(`/api/endpoints/${current.endpoint}/desktop/stop`, {
          method: "POST",
          body: JSON.stringify({ session_id: current.session }),
          keepalive: true,
        }).catch(() => {});
      }
    },
    [],
  );

  async function action(work: () => Promise<unknown>) {
    setError("");
    setBusy(true);
    try {
      await work();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Thao tác thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    abort.current?.abort();
    abort.current = null;
    sessionRef.current = null;
    setSession(null);
    setControl(false);
    setFrame(null);
    if (session) {
      await apiJson(`${prefix}/desktop/stop`, {
        method: "POST",
        body: JSON.stringify({ session_id: session.session_id }),
      });
    }
  }

  async function start() {
    const current = await apiJson<Session>(`${prefix}/desktop/session`, {
      method: "POST",
      body: JSON.stringify({ monitor }),
    });
    setSession(current);
    sequence.current = 0;
    sessionRef.current = { endpoint: selected!.endpoint_id, session: current.session_id };
    const controller = new AbortController();
    abort.current = controller;
    void (async () => {
      try {
        const response = await apiFetch(`${prefix}/desktop/frames`, {
          headers: { "X-Desktop-Session": current.session_id },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error("Luồng màn hình không khả dụng.");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          if (buffer.length > 1500000) throw new Error("Khung hình vượt giới hạn.");
          let newline;
          while ((newline = buffer.indexOf("\n")) >= 0) {
            const next = JSON.parse(buffer.slice(0, newline)) as Frame;
            buffer = buffer.slice(newline + 1);
            setFrame(next);
          }
        }
        if (!controller.signal.aborted) throw new Error("Thiết bị đã ngắt kết nối.");
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : "Thiết bị đã ngắt kết nối.");
      } finally {
        if (abort.current === controller) {
          sessionRef.current = null;
          setSession(null);
          setControl(false);
          setFrame(null);
          abort.current = null;
        }
      }
    })();
  }

  async function input(operation: string, args: object) {
    if (!control || !session || inputPending.current) return;
    inputPending.current = true;
    try {
      await apiJson(`${prefix}/desktop/input`, {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          sequence: ++sequence.current,
          operation: `desktop.${operation}`,
          arguments: args,
        }),
      });
    } catch (reason) {
      if (sessionRef.current?.session === session.session_id) {
        setControl(false);
        setError(reason instanceof Error ? reason.message : "Điều khiển đã dừng.");
        void stop().catch(() => {});
      }
    } finally {
      inputPending.current = false;
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <PageHeader
        title="Remote Control"
        subtitle="Portable worker · Device Chat · Màn hình từ xa"
      />
      <div className="space-y-4 p-6">
        {error && <p role="alert">{error}</p>}
        <p>
          Worker {artifacts?.version ?? "phiên bản hiện tại"} · Không cần Python/Node/npm · Windows
          x64, Linux x86_64 (glibc 2.35+).
        </p>
        {artifacts?.available ? (
          artifacts.artifacts.map((artifact) => (
            <div key={artifact.platform}>
              <a href={artifact.url} rel="noreferrer">
                {artifact.platform === "windows-x64"
                  ? "Download Windows portable worker"
                  : "Download Linux portable worker"}
              </a>
              <p>
                SHA-256: <code>{artifact.sha256}</code>
              </p>
            </div>
          ))
        ) : (
          <p role="status">Artifact unavailable for this build</p>
        )}
        <Button
          disabled={busy}
          onClick={() =>
            void action(async () => {
              const result = await apiJson<{ token: string; expires_at: number }>(
                "/api/endpoints/pairing-tokens",
                {
                  method: "POST",
                },
              );
              setToken(result.token);
              setExpires(result.expires_at ?? Date.now() / 1000 + 300);
            })
          }
        >
          Tạo mã ghép nối tạm thời
        </Button>
        {token && (
          <div>
            <p>Mã dùng một lần · hết hạn sau {remaining} giây:</p>
            <code>{token}</code>
            <Button onClick={() => setToken("")}>Ẩn mã</Button>
          </div>
        )}
        <ul className="space-y-2">
          {devices.map((device) => (
            <li key={device.endpoint_id}>
              <Button
                variant="outline"
                disabled={!!session}
                onClick={() => {
                  setSelected(device);
                  setLabel(device.name);
                  setMonitor(1);
                  setPath("");
                  setTab("Chat");
                }}
              >
                {device.name} · {device.platform ?? "Chưa kết nối"} ·{" "}
                {device.revoked_at ? "Đã thu hồi" : device.online ? "Online" : "Offline"}
              </Button>
              <span>
                {" "}
                · {device.temporary ? "Tạm thời" : "Đã nhớ"} ·{" "}
                {device.os_release ?? "OS chưa quan sát"} ·{" "}
                {device.architecture ?? "Kiến trúc chưa quan sát"} · Worker{" "}
                {device.worker_version ?? "chưa kết nối"}
              </span>
              {device.system_summary && (
                <span>
                  {" "}
                  · CPU {device.system_summary.cpu_count ?? "?"} · RAM{" "}
                  {Math.round((device.system_summary.memory_total ?? 0) / 1024 ** 3)} GiB (quan sát
                  trong 5 phút)
                </span>
              )}
              <span>
                {" "}
                · Màn hình{" "}
                {device.capabilities.includes("screen.capture")
                  ? "khả dụng"
                  : "tắt/không khả dụng"}{" "}
                · Browser{" "}
                {device.capabilities.includes("browser.open") ? "khả dụng" : "tắt/chưa provision"}
              </span>
            </li>
          ))}
        </ul>
        {selected && (
          <section className="space-y-3" aria-label="Chi tiết thiết bị">
            <h2>{selected.name}</h2>
            <code>{selected.endpoint_id}</code>
            <p>{selected.capabilities.join(", ")}</p>
            <div role="tablist" aria-label="Không gian thiết bị">
              {["Chat", "Desktop", "Files", "Processes", "Browser", "Connection"].map((name) => (
                <Button
                  role="tab"
                  aria-selected={tab === name}
                  key={name}
                  disabled={!!session && name !== "Desktop"}
                  onClick={() => setTab(name)}
                >
                  {name}
                </Button>
              ))}
            </div>
            {tab === "Chat" && (
              <DeviceChat key={selected.endpoint_id} endpointId={selected.endpoint_id} />
            )}
            {(tab === "Processes" || tab === "Browser") && (
              <EndpointOperations
                key={`${selected.endpoint_id}-${tab}`}
                endpointId={selected.endpoint_id}
                surface={tab}
                online={selected.online}
              />
            )}
            {tab === "Connection" && (
              <>
                <Button
                  disabled={busy || !selected.online}
                  onClick={() =>
                    void action(async () => {
                      await apiJson(`${prefix}/operation`, {
                        method: "POST",
                        body: JSON.stringify({ operation: "system.inspect", arguments: {} }),
                      });
                      await load();
                    })
                  }
                >
                  Quan sát system
                </Button>
                <Input
                  aria-label="Tên thiết bị"
                  value={label}
                  maxLength={120}
                  onChange={(event) => setLabel(event.target.value)}
                />
                <Button
                  disabled={busy || !label.trim()}
                  onClick={() =>
                    void action(async () => {
                      await apiJson(prefix, {
                        method: "PATCH",
                        body: JSON.stringify({ name: label }),
                      });
                      await load();
                    })
                  }
                >
                  Đổi tên
                </Button>
                <Button
                  disabled={busy || !!selected.revoked_at}
                  onClick={() =>
                    void action(async () => {
                      await apiJson(`${prefix}/revoke`, { method: "POST" });
                      abort.current?.abort();
                      await load();
                    })
                  }
                >
                  Thu hồi thiết bị
                </Button>
                <Button
                  disabled={busy}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "End & forget: Thu hồi thiết bị và xóa toàn bộ Device Chat/lịch sử thiết bị?",
                      )
                    )
                      return;
                    void action(async () => {
                      await apiJson(`${prefix}/forget`, {
                        method: "POST",
                        body: JSON.stringify({ confirmed: true }),
                      });
                      setSelected(null);
                      await load();
                    });
                  }}
                >
                  End &amp; forget
                </Button>
                <p>
                  Lần thấy gần nhất:{" "}
                  {selected.last_seen
                    ? new Date(selected.last_seen * 1000).toLocaleString()
                    : "chưa kết nối"}
                </p>
              </>
            )}
            {tab === "Files" && (
              <>
                <Input
                  aria-label="Đường dẫn file"
                  value={path}
                  maxLength={2048}
                  onChange={(event) => setPath(event.target.value)}
                />
                <label>
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(event) => setOverwrite(event.target.checked)}
                  />{" "}
                  Cho phép ghi đè
                </label>
                <input
                  aria-label="Tải file lên"
                  type="file"
                  disabled={busy || !selected.online || !path}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    void action(async () => {
                      if (file.size > 32 * 1024 * 1024) throw new Error("File vượt 32 MiB.");
                      const response = await apiFetch(`${prefix}/upload`, {
                        method: "POST",
                        headers: {
                          "X-Endpoint-Path": path,
                          "X-Overwrite": String(overwrite),
                          "Content-Type": "application/octet-stream",
                        },
                        body: file,
                      });
                      if (!response.ok) throw new Error("Tải lên thất bại.");
                    });
                    event.target.value = "";
                  }}
                />
                <Button
                  disabled={busy || !selected.online || !path}
                  onClick={() =>
                    void action(async () => {
                      const response = await apiFetch(`${prefix}/download`, {
                        method: "POST",
                        body: JSON.stringify({ path }),
                      });
                      if (!response.ok) throw new Error("Tải xuống thất bại.");
                      const url = URL.createObjectURL(await response.blob());
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = "endpoint-download";
                      link.click();
                      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                    })
                  }
                >
                  Tải xuống
                </Button>
              </>
            )}
            {tab === "Desktop" && (
              <>
                <div>
                  <label>
                    Màn hình{" "}
                    <select
                      aria-label="Chọn màn hình"
                      value={monitor}
                      disabled={!!session}
                      onChange={(event) => setMonitor(Number(event.target.value))}
                    >
                      {(selected.geometry?.length
                        ? selected.geometry
                        : [{ width: 0, height: 0 }]
                      ).map((display, index) => (
                        <option key={index} value={index + 1}>
                          {index + 1} · {display.width} × {display.height}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p role="status">
                    {session
                      ? control
                        ? "Đã kết nối · Điều khiển bật"
                        : "Đã kết nối · Chỉ xem"
                      : "Chưa mở phiên màn hình"}
                  </p>
                  <Button
                    disabled={
                      busy ||
                      !!session ||
                      !selected.online ||
                      !selected.capabilities.includes("screen.capture")
                    }
                    onClick={() => void action(start)}
                  >
                    Xem màn hình
                  </Button>
                  <Button disabled={busy || !session} onClick={() => void action(stop)}>
                    Dừng phiên
                  </Button>
                  <Button
                    disabled={busy || !session?.control_available}
                    onClick={() =>
                      void action(async () => {
                        await apiJson(`${prefix}/desktop/control`, {
                          method: "POST",
                          body: JSON.stringify({
                            session_id: session!.session_id,
                            enabled: !control,
                          }),
                        });
                        setControl(!control);
                      })
                    }
                  >
                    {control ? "Tắt điều khiển" : "Bật điều khiển"}
                  </Button>
                </div>
                {frame && (
                  <img
                    src={`data:image/jpeg;base64,${frame.image_b64}`}
                    alt="Màn hình thiết bị từ xa"
                    tabIndex={0}
                    className="max-w-full border"
                    onClick={(event) => {
                      const box = event.currentTarget.getBoundingClientRect();
                      void input("click", {
                        monitor,
                        x: Math.min(
                          frame.geometry.width - 1,
                          Math.floor(
                            ((event.clientX - box.left) * frame.geometry.width) / box.width,
                          ),
                        ),
                        y: Math.min(
                          frame.geometry.height - 1,
                          Math.floor(
                            ((event.clientY - box.top) * frame.geometry.height) / box.height,
                          ),
                        ),
                        button: "left",
                      });
                    }}
                    onPointerMove={(event) => {
                      const box = event.currentTarget.getBoundingClientRect();
                      void input("move", {
                        monitor,
                        x: Math.min(
                          frame.geometry.width - 1,
                          Math.floor(
                            ((event.clientX - box.left) * frame.geometry.width) / box.width,
                          ),
                        ),
                        y: Math.min(
                          frame.geometry.height - 1,
                          Math.floor(
                            ((event.clientY - box.top) * frame.geometry.height) / box.height,
                          ),
                        ),
                      });
                    }}
                    onWheel={(event) => {
                      if (control) {
                        event.preventDefault();
                        void input("scroll", { dx: 0, dy: event.deltaY > 0 ? -1 : 1 });
                      }
                    }}
                    onKeyDown={(event) => {
                      const mapping: Record<string, string> = {
                        Enter: "enter",
                        Tab: "tab",
                        Escape: "escape",
                        Backspace: "backspace",
                        Delete: "delete",
                        ArrowUp: "up",
                        ArrowDown: "down",
                        ArrowLeft: "left",
                        ArrowRight: "right",
                        Home: "home",
                        End: "end",
                        " ": "space",
                      };
                      if (control && mapping[event.key]) {
                        event.preventDefault();
                        void input("key", { key: mapping[event.key] });
                      }
                    }}
                  />
                )}
                <Input
                  aria-label="Văn bản gửi đến thiết bị"
                  value={text}
                  maxLength={4096}
                  type="password"
                  onChange={(event) => setText(event.target.value)}
                />
                <Button
                  disabled={!control}
                  onClick={() => {
                    void input("type", { text });
                    setText("");
                  }}
                >
                  Gửi văn bản
                </Button>
              </>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function EndpointOperations({
  endpointId,
  surface,
  online,
}: {
  endpointId: string;
  surface: string;
  online: boolean;
}) {
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [value, setValue] = useState("");
  const [selector, setSelector] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [processes, setProcesses] = useState<
    Array<{ pid: number; name: string; created_at: number }>
  >([]);
  async function call(operation: string, args: object) {
    setBusy(true);
    setError("");
    try {
      const data = await apiJson<Record<string, unknown>>(
        `/api/endpoints/${endpointId}/operation`,
        {
          method: "POST",
          body: JSON.stringify({ operation, arguments: args }),
        },
      );
      setResult(JSON.stringify(data, null, 2).slice(0, 30000));
      if (operation === "process.list") setProcesses(data.processes as typeof processes);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Endpoint operation failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={surface} className="space-y-2">
      {error && <p role="alert">{error}</p>}
      <Input
        aria-label={surface === "Processes" ? "Application alias" : "Browser URL"}
        value={value}
        maxLength={surface === "Processes" ? 64 : 2048}
        onChange={(event) => setValue(event.target.value)}
      />
      {surface === "Processes" ? (
        <>
          <Button disabled={busy || !online} onClick={() => void call("process.list", {})}>
            Liệt kê tiến trình
          </Button>
          <Button
            disabled={busy || !online || !value}
            onClick={() => void call("process.start", { alias: value, args: [] })}
          >
            Khởi chạy alias
          </Button>
          {processes.map((process) => (
            <div key={process.pid}>
              {process.name} · {process.pid}
              <Button
                disabled={busy || !online}
                onClick={() => {
                  if (window.confirm(`Dừng ${process.name} (${process.pid})?`))
                    void call("process.terminate", {
                      pid: process.pid,
                      expected_name: process.name,
                      expected_created_at: process.created_at,
                    });
                }}
              >
                Dừng tiến trình
              </Button>
            </div>
          ))}
        </>
      ) : (
        <>
          <Button
            disabled={busy || !online || !value}
            onClick={() => void call("browser.open", { url: value })}
          >
            Mở browser riêng
          </Button>
          <Button
            disabled={busy || !online || !value}
            onClick={() => void call("browser.navigate", { url: value })}
          >
            Đi đến URL
          </Button>
          <Button disabled={busy || !online} onClick={() => void call("browser.snapshot", {})}>
            Snapshot
          </Button>
          <Input
            aria-label="Browser selector"
            value={selector}
            maxLength={512}
            onChange={(event) => setSelector(event.target.value)}
          />
          <Input
            aria-label="Browser text"
            type="password"
            value={text}
            maxLength={4096}
            onChange={(event) => setText(event.target.value)}
          />
          <Button
            disabled={busy || !online || !selector}
            onClick={() => void call("browser.click", { selector })}
          >
            Click
          </Button>
          <Button
            disabled={busy || !online || !selector}
            onClick={() => {
              void call("browser.type", { selector, text });
              setText("");
            }}
          >
            Điền browser
          </Button>
          <Button
            disabled={busy || !online}
            onClick={() => void call("browser.key", { key: "enter" })}
          >
            Enter
          </Button>
          <Button disabled={busy || !online} onClick={() => void call("browser.close", {})}>
            Đóng browser
          </Button>
        </>
      )}
      <pre className="overflow-auto whitespace-pre-wrap">{result}</pre>
    </section>
  );
}
