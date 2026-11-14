import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import type { Schemas } from "@/lib/sdk/generated";
import {
  activeServer,
  activeHostOrigin,
  activeHostStop,
  desktopHostSettings,
  type HostSettingsOptions,
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
} from "@/lib/server-profiles";

function HostSettingsPanel() {
  const bridge = desktopHostSettings();
  const [settings, setSettings] = useState<HostSettingsOptions | null>(null);
  const [passwordHash, setPasswordHash] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    void bridge
      ?.load()
      .then(setSettings)
      .catch(() => setError("Không đọc được cấu hình Host Mode."));
  }, [bridge]);
  if (!bridge) return null;
  return (
    <form
      className="space-y-2 rounded border p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        if (!settings || saving) return;
        setSaving(true);
        setError("");
        void bridge.save({ ...settings, passwordHash }).catch(() => {
          setError("Không lưu được. Kiểm tra địa chỉ HTTPS và mã băm Argon2id.");
          setSaving(false);
        });
      }}
    >
      <h3 className="font-medium">Cấu hình Host Mode</h3>
      {settings && (
        <>
          <label className="block">
            <input
              type="checkbox"
              checked={settings.enabled}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  enabled: e.target.checked,
                })
              }
            />{" "}
            Bật Host Mode
          </label>
          {settings.enabled && (
            <>
              <label className="block">
                Địa chỉ HTTPS
                <input
                  className="block w-full rounded border bg-background px-2"
                  type="url"
                  required
                  value={settings.origin}
                  onChange={(e) => setSettings({ ...settings, origin: e.target.value })}
                />
              </label>
              <label className="block">
                Mã băm mật khẩu Argon2id
                <input
                  autoComplete="off"
                  className="block w-full rounded border bg-background px-2"
                  type="password"
                  placeholder="Bỏ trống để giữ mã băm hiện có"
                  value={passwordHash}
                  onChange={(e) => setPasswordHash(e.target.value)}
                />
              </label>
              <label className="block">
                <input
                  type="checkbox"
                  checked={settings.autostart}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      autostart: e.target.checked,
                    })
                  }
                />{" "}
                Chạy khi đăng nhập Windows
              </label>
            </>
          )}
          <button type="submit" disabled={saving} className="rounded border px-2 py-1">
            Lưu và khởi động lại Orion
          </button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </form>
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
  const [enrollment, setEnrollment] = useState<Schemas["NativeEnrollmentCode"] | null>(null);
  const current = activeServer();
  const nativePath = "/api/auth/native";
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
      <HostSettingsPanel />
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
                  setEnrollment(
                    await apiJson<Schemas["NativeEnrollmentCode"]>(
                      nativePath + "/enrollment-codes",
                      { method: "POST" },
                    ),
                  );
                })
              }
            >
              Tạo mã kết nối
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
            <p role="status">
              Mã dùng một lần <code>{enrollment.code}</code> · Hết hạn{" "}
              {new Date(enrollment.expires_at * 1000).toLocaleTimeString("vi-VN")}
            </p>
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
            void enrollServer(code, "Orion client")
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
