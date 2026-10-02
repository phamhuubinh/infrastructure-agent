import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
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
  geometry?: Array<{ width: number; height: number }>;
};
type Frame = {
  image_b64: string;
  width: number;
  height: number;
  geometry: { width: number; height: number };
};
type Session = { session_id: string; control_available: boolean };

export function EndpointsPage() {
  const [devices, setDevices] = useState<Endpoint[]>([]);
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
      <PageHeader title="Thiết bị" subtitle="Thiết bị đã ghép nối và màn hình từ xa" />
      <div className="space-y-4 p-6">
        {error && <p role="alert">{error}</p>}
        <Button
          disabled={busy}
          onClick={() =>
            void action(async () => {
              const result = await apiJson<{ token: string }>("/api/endpoints/pairing-tokens", {
                method: "POST",
              });
              setToken(result.token);
              window.setTimeout(() => setToken(""), 300000);
            })
          }
        >
          Tạo mã ghép nối
        </Button>
        {token && (
          <div>
            <p>Mã dùng một lần, hết hạn sau 5 phút:</p>
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
                }}
              >
                {device.name} · {device.platform ?? "Chưa kết nối"} ·{" "}
                {device.revoked_at ? "Đã thu hồi" : device.online ? "Online" : "Offline"}
              </Button>
            </li>
          ))}
        </ul>
        {selected && (
          <section className="space-y-3" aria-label="Chi tiết thiết bị">
            <h2>{selected.name}</h2>
            <code>{selected.endpoint_id}</code>
            <p>{selected.capabilities.join(", ")}</p>
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
                  await apiJson(prefix, { method: "PATCH", body: JSON.stringify({ name: label }) });
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
            <div>
              <label>
                Màn hình{" "}
                <select
                  aria-label="Chọn màn hình"
                  value={monitor}
                  disabled={!!session}
                  onChange={(event) => setMonitor(Number(event.target.value))}
                >
                  {(selected.geometry?.length ? selected.geometry : [{ width: 0, height: 0 }]).map(
                    (display, index) => (
                      <option key={index} value={index + 1}>
                        {index + 1} · {display.width} × {display.height}
                      </option>
                    ),
                  )}
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
                      body: JSON.stringify({ session_id: session!.session_id, enabled: !control }),
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
                      Math.floor(((event.clientX - box.left) * frame.geometry.width) / box.width),
                    ),
                    y: Math.min(
                      frame.geometry.height - 1,
                      Math.floor(((event.clientY - box.top) * frame.geometry.height) / box.height),
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
                      Math.floor(((event.clientX - box.left) * frame.geometry.width) / box.width),
                    ),
                    y: Math.min(
                      frame.geometry.height - 1,
                      Math.floor(((event.clientY - box.top) * frame.geometry.height) / box.height),
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
          </section>
        )}
      </div>
    </div>
  );
}
