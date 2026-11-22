import { useEffect, useState } from "react";
import { AndroidConnectionQr } from "./AndroidConnectionQr";
import { OwnerSecurity } from "./OwnerSecurity";
import { PrivateQr } from "./PrivateQr";
import { apiJson } from "@/lib/api";
import { observeHostRefresh } from "@/lib/host-refresh";
import type { Schemas } from "@/lib/sdk/generated";
import {
  activeServer,
  activeHostOrigin,
  activeHostStop,
  desktopTailscaleStatus,
  type TailscaleStatus,
  activateManagedServer,
  activateServer,
  hasActiveServer,
  hasManagedServer,
  managedServerError,
  saveServerProfile,
  serverProfiles,
  removeServerProfile,
  isNativeHost,
  isManagedServer,
  enrollServer,
  desktopTailscaleToggle,
  desktopInternetToggle,
} from "@/lib/server-profiles";

const tailscaleMessages: Record<string, string> = {
  not_installed: "Chưa cài Tailscale.",
  unavailable: "Không đọc được trạng thái Tailscale.",
  login_required: "Đăng nhập Tailscale hoặc duyệt thiết bị trong tailnet.",
  offline: "Tailscale chưa kết nối.",
  no_dns: "Chưa có tên DNS Tailscale cho thiết bị này.",
  host_disabled: "Bật Host Mode để dùng Serve.",
  origin_mismatch: "Đặt địa chỉ HTTPS của Host Mode theo tên Tailscale.",
  serve_unavailable: "Không đọc được cấu hình Tailscale Serve.",
  unconfigured: "Chưa cấu hình Serve HTTPS.",
  different_backend: "Serve đang trỏ tới backend khác. Kiểm tra cấu hình trước khi thay đổi.",
  public: "Truy cập Internet qua Funnel đang bật. Orion yêu cầu Owner và TOTP.",
  enable_failed: "Orion chưa bật được Serve. Kiểm tra quyền Administrator.",
  configured: "Serve đã trỏ tới backend Orion.",
};

const probeMessages: Record<string, string> = {
  login_ready: "HTTPS hoạt động. API yêu cầu đăng nhập Owner và 2FA.",
  auth_required: "HTTPS phản hồi 401/403. Chưa xác minh được trang đăng nhập.",
  timeout: "HTTPS quá thời gian chờ.",
  tls: "Không xác minh được TLS hoặc chứng chỉ HTTPS.",
  dns: "Không phân giải được tên Tailscale.",
  connect: "Không kết nối được tới Serve.",
  backend_unavailable: "Backend Orion không phản hồi qua loopback.",
  upstream_proxy: "Serve phản hồi lỗi proxy 502–504.",
  origin_rejected: "Orion từ chối Origin của URL HTTPS.",
  auth_mismatch: "Phản hồi xác thực Owner không khớp.",
  invalid_response: "Serve trả về phản hồi không khớp Orion.",
  probe_unavailable: "Không chạy được kiểm tra HTTPS trên Windows.",
};

export function TailscalePanel() {
  const check = desktopTailscaleStatus();
  const toggle = desktopTailscaleToggle();
  const internet = desktopInternetToggle();
  const [confirmedPublic, setConfirmedPublic] = useState(false);
  const [status, setStatus] = useState<TailscaleStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (!check || busy) return;
    let active = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const result = await check?.();
        if (active && result) setStatus(result);
      } catch {
        if (active) setStatus(null);
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 15000);
      }
    }
    void poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [check, busy]);
  if (!check) return null;
  async function refresh(action: () => Promise<TailscaleStatus>) {
    setBusy(true);
    setFailed("");
    try {
      setStatus(await action());
    } catch (error) {
      setFailed(typeof error === "string" ? error : "Không thực hiện được thao tác Tailscale.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2 rounded border p-3 text-sm">
      <h3 className="font-medium">Tailscale Serve</h3>
      {toggle && (
        <div className="flex flex-wrap gap-2">
          {(!status?.enabled || !!status.error || status.state === "unconfigured") && (
            <button
              type="button"
              className="rounded border px-2 py-1"
              disabled={busy}
              onClick={() => void refresh(() => toggle(true))}
            >
              Bật truy cập từ xa
            </button>
          )}
          {(status?.enabled || !!activeHostStop()) && (
            <button
              type="button"
              className="rounded border px-2 py-1"
              disabled={busy}
              onClick={() => void refresh(() => toggle(false))}
            >
              Tắt truy cập từ xa
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            className="rounded border px-2 py-1"
            onClick={() => void refresh(check)}
          >
            Kiểm tra kết nối
          </button>
        </div>
      )}
      {busy && <p role="status">Đang cập nhật truy cập từ xa…</p>}
      {internet && (
        <div className="space-y-2 border-t pt-2">
          {status?.state !== "public" && (
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={confirmedPublic}
                disabled={busy}
                onChange={(event) => setConfirmedPublic(event.target.checked)}
              />
              Tôi đồng ý công khai URL Orion trên Internet. Người truy cập phải đăng nhập Owner và
              TOTP.
            </label>
          )}
          <button
            type="button"
            className="rounded border px-2 py-1"
            disabled={
              busy || (status?.state !== "public" && (!confirmedPublic || !status?.reachable))
            }
            onClick={() => {
              const enable = status?.state !== "public";
              void refresh(() => internet(enable, enable && confirmedPublic));
              setConfirmedPublic(false);
            }}
          >
            {status?.state === "public" ? "Tắt truy cập qua Internet" : "Bật truy cập qua Internet"}
          </button>
          <p>
            Bật Host Mode và Serve HTTPS trước khi bật Internet. Tắt Internet sẽ quay về Serve riêng
            tư.
          </p>
        </div>
      )}
      {(failed || status?.error) && <p role="alert">{failed || status?.error}</p>}
      {status && (
        <div role="status">
          <p>
            {status.reachable ? "Online" : "Offline"} · {tailscaleMessages[status.state]}
          </p>
          {status.url && (
            <p className="break-all">
              {status.state === "public" ? "URL Internet" : "URL tailnet"} · {status.url}
            </p>
          )}
          {status.backend && <p>Backend · {status.backend}</p>}
          {status.probe && <p>{probeMessages[status.probe]}</p>}
        </div>
      )}
    </div>
  );
}

export function ServerConnections() {
  const [profiles, setProfiles] = useState(serverProfiles);
  const [name, setName] = useState("");
  const [origin, setOrigin] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [clients, setClients] = useState<ReadonlyArray<Schemas["NativeSessionView"]>>([]);
  const [enrollment, setEnrollment] = useState<
    (Schemas["NativeEnrollmentCode"] & { origin: string }) | null
  >(null);
  useEffect(() => {
    if (!enrollment) return;
    const timer = window.setTimeout(
      () => setEnrollment(null),
      Math.max(0, enrollment.expires_at * 1000 - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [enrollment]);
  const current = activeServer();
  const nativePath = "/api/auth/native";
  useEffect(() => {
    if (!hasActiveServer()) return;
    return observeHostRefresh(async (current) => {
      const rows = await apiJson<ReadonlyArray<Schemas["NativeSessionView"]>>(
        nativePath + "/sessions",
      );
      if (current()) setClients(rows);
    });
  }, [current.id, current.origin]);
  async function refreshClients() {
    setClients(
      await apiJson<ReadonlyArray<Schemas["NativeSessionView"]>>(nativePath + "/sessions"),
    );
  }
  async function manageClients(action: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    try {
      await action();
    } catch {
      setNotice("Không thể cập nhật kết nối của thiết bị.");
    } finally {
      setBusy(false);
    }
  }
  const stopHost = activeHostStop();
  const backendError = managedServerError();
  return (
    <section aria-label="Kết nối server" className="space-y-3 rounded-lg border p-4">
      <h2 className="font-semibold">Kết nối server</h2>
      <OwnerSecurity />
      <TailscalePanel />
      {stopHost && (
        <div className="flex items-center gap-3 text-sm">
          <span>Host Mode đang chạy · {activeHostOrigin()}</span>
          <button
            type="button"
            className="rounded border px-2 py-1"
            onClick={() => void stopHost().catch(() => setNotice("Không thể dừng server."))}
          >
            Dừng server và đóng Orion
          </button>
        </div>
      )}
      {stopHost && isManagedServer() && (
        <div className="space-y-2 text-sm">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void manageClients(async () => {
                  const status = await desktopTailscaleStatus()?.();
                  if (
                    status?.state !== "configured" ||
                    status.probe !== "login_ready" ||
                    !status.url
                  ) {
                    setNotice("Cần Tailscale Serve đang hoạt động trước khi tạo QR.");
                    return;
                  }
                  const grant = await apiJson<Schemas["NativeEnrollmentCode"]>(
                    nativePath + "/enrollment-codes",
                    { method: "POST" },
                  );
                  setEnrollment({ ...grant, origin: status.url });
                })
              }
            >
              Tạo QR kết nối
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void manageClients(refreshClients)}
            >
              Tải danh sách thiết bị
            </button>
          </div>
          {enrollment && (
            <div className="space-y-2">
              <p role="status">
                QR kết nối Android · Hết hạn{" "}
                {new Date(enrollment.expires_at * 1000).toLocaleTimeString("vi-VN")}
              </p>
              <PrivateQr
                label="QR kết nối Android"
                value={JSON.stringify({
                  type: "orion-connect",
                  version: 1,
                  origin: enrollment.origin,
                  code: enrollment.code,
                })}
              />
              <button
                type="button"
                className="rounded border px-2 py-1"
                onClick={() => setEnrollment(null)}
              >
                Ẩn QR
              </button>
            </div>
          )}
          <ul>
            {clients
              .filter((client) => !client.revoked_at)
              .map((client) => (
                <li key={client.session_id} className="flex items-center gap-2">
                  <span>
                    {client.name} · {client.platform}
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void manageClients(async () => {
                        await apiJson(
                          nativePath +
                            "/sessions/" +
                            encodeURIComponent(client.session_id) +
                            "/revoke",
                          { method: "POST" },
                        );
                        await refreshClients();
                      })
                    }
                  >
                    Thu hồi
                  </button>
                </li>
              ))}
          </ul>
        </div>
      )}
      {backendError && (
        <p role="alert" className="text-sm">
          {backendError} Chi tiết trong managed/desktop-backend.log nếu ghi được nhật ký.
        </p>
      )}
      {hasActiveServer() && (
        <p className="break-all text-sm">
          {current.name} · {current.origin}
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Web mở server trong đúng origin đăng nhập. Ứng dụng native dùng mã kết nối do chủ server
        cấp.
      </p>
      <ul className="space-y-2">
        {hasManagedServer() && !isManagedServer() && (
          <li>
            <button
              type="button"
              className="rounded border px-2 py-1"
              onClick={activateManagedServer}
            >
              Mở Orion trên máy này
            </button>
          </li>
        )}
        {profiles.map((profile) => (
          <li key={profile.id} className="flex flex-wrap gap-2 items-center">
            <span>
              {profile.name} · {profile.origin}
            </span>
            <button
              type="button"
              className="rounded border px-2 py-1"
              onClick={() => {
                try {
                  activateServer(profile);
                } catch {
                  setNotice("Không thể mở server này.");
                }
              }}
            >
              Mở {profile.name}
            </button>
            <button
              type="button"
              disabled={profile.id === current.id}
              className="rounded border px-2 py-1"
              onClick={() => {
                try {
                  removeServerProfile(profile.id);
                  setProfiles(serverProfiles());
                } catch {
                  setNotice("Không thể xóa server đang dùng.");
                }
              }}
            >
              Xóa {profile.name}
            </button>
          </li>
        ))}
      </ul>
      <AndroidConnectionQr />
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          try {
            saveServerProfile(name, origin);
            setProfiles(serverProfiles());
            setName("");
            setOrigin("");
            setNotice("");
          } catch {
            setNotice("Kiểm tra tên, HTTPS hoặc địa chỉ loopback và server trùng.");
          }
        }}
      >
        <label>
          Tên server
          <input
            className="block rounded border bg-background p-2"
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Địa chỉ server
          <input
            className="block rounded border bg-background p-2"
            required
            type="url"
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
            placeholder="https://orion.example"
          />
        </label>
        <button type="submit" className="self-end rounded border px-3 py-2">
          Lưu server
        </button>
      </form>
      {isNativeHost() && hasActiveServer() && !isManagedServer() && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setBusy(true);
            setNotice("");
            const form = event.currentTarget;
            const fields = new FormData(form);
            const password = String(fields.get("owner-password") ?? "");
            const totp_code = String(fields.get("owner-code") ?? "").trim();
            form.reset();
            void enrollServer(
              code,
              "Orion client",
              password || totp_code ? { password, totp_code } : undefined,
            )
              .then(() => {
                setCode("");
                setNotice("Đã kết nối.");
              })
              .catch(() => setNotice("Mã kết nối không hợp lệ hoặc đã hết hạn."))
              .finally(() => setBusy(false));
          }}
        >
          <label>
            Mã kết nối
            <input
              className="block rounded border bg-background p-2"
              type="password"
              autoComplete="off"
              required
              value={code}
              maxLength={128}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <label>
            Mật khẩu Owner
            <input
              name="owner-password"
              className="block rounded border bg-background p-2"
              type="password"
              autoComplete="current-password"
              maxLength={1024}
            />
          </label>
          <label>
            Mã Authenticator hoặc mã khôi phục
            <input
              name="owner-code"
              className="block rounded border bg-background p-2"
              autoComplete="one-time-code"
              maxLength={64}
            />
          </label>
          <button type="submit" disabled={busy} className="self-end rounded border px-3 py-2">
            Kết nối bằng mã
          </button>
        </form>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
    </section>
  );
}
