import { useEffect, useState, type FormEvent } from "react";
import { apiJson } from "@/lib/api";
import { desktopHostSettings, isManagedServer } from "@/lib/server-profiles";
import { PrivateQr } from "./PrivateQr";

const root = "/api/auth/owner";
type Setup = { setup_id: string; otpauth_uri: string };
type Mode = "setup" | "password" | "totp" | "revoke-all";

function post<T>(path: string, data: Record<string, string>) {
  return apiJson<T>(root + path, { method: "POST", body: JSON.stringify(data) });
}

export function OwnerSecurity() {
  const available = !!desktopHostSettings() && isManagedServer();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [mode, setMode] = useState<Mode>("setup");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [recovery, setRecovery] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!available) return;
    let active = true;
    void apiJson<{ configured: boolean }>(root)
      .then((state) => {
        if (!active) return;
        setConfigured(state.configured);
        setMode(state.configured ? "password" : "setup");
      })
      .catch(() => {
        if (active) setNotice("Không đọc được trạng thái tài khoản Owner.");
      });
    return () => {
      active = false;
    };
  }, [available]);

  if (!available) return null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const password = String(fields.get("password") ?? "");
    const code = String(fields.get("code") ?? "");
    const newPassword = String(fields.get("new_password") ?? "");
    setBusy(true);
    setNotice("");
    try {
      if (setup) {
        const path = mode === "setup" ? "/setup/confirm" : "/totp/confirm";
        const result = await post<{ recovery_codes: string[] }>(path, {
          setup_id: setup.setup_id,
          code,
        });
        setRecovery(result.recovery_codes);
        setSetup(null);
        setConfigured(true);
        setMode("password");
      } else if (mode === "setup" || mode === "totp") {
        const path = mode === "setup" ? "/setup/start" : "/totp/start";
        setSetup(await post<Setup>(path, mode === "setup" ? { password } : { password, code }));
      } else {
        await post(
          mode === "password" ? "/password" : "/revoke-all",
          mode === "password"
            ? { current_password: password, code, new_password: newPassword }
            : { password, code },
        );
        setNotice(mode === "password" ? "Đã cập nhật mật khẩu." : "Đã thu hồi các phiên từ xa.");
      }
      form.reset();
    } catch {
      setNotice("Không thực hiện được. Kiểm tra mật khẩu, mã xác thực và trạng thái thiết lập.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Tài khoản và bảo mật" className="space-y-2 rounded border p-3 text-sm">
      <h3 className="font-medium">Tài khoản &amp; Bảo mật</h3>
      {notice && <p role="status">{notice}</p>}
      {recovery.length > 0 ? (
        <>
          <p>Lưu các mã khôi phục này ở nơi an toàn. Mỗi mã chỉ dùng được một lần.</p>
          <ul className="font-mono">
            {recovery.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <button
            type="button"
            className="rounded border px-2 py-1"
            onClick={() => setRecovery([])}
          >
            Đã lưu mã
          </button>
        </>
      ) : (
        configured !== null && (
          <form
            key={mode + (setup ? "-confirm" : "")}
            className="space-y-2"
            onSubmit={(event) => void submit(event)}
          >
            {configured && !setup && (
              <label className="block">
                Mật khẩu &amp; 2FA
                <select
                  className="ml-2 rounded border bg-background px-2 py-1"
                  value={mode}
                  disabled={busy}
                  onChange={(event) => setMode(event.target.value as Mode)}
                >
                  <option value="password">Đổi mật khẩu</option>
                  <option value="totp">Thay đổi 2FA</option>
                  <option value="revoke-all">Đăng xuất tất cả thiết bị</option>
                </select>
              </label>
            )}
            {setup && (
              <>
                <p>Quét QR Authenticator rồi nhập mã mới để xác nhận.</p>
                <PrivateQr label="QR Authenticator" value={setup.otpauth_uri} />
                <button
                  type="button"
                  className="rounded border px-2 py-1"
                  onClick={() => setSetup(null)}
                >
                  Hủy thiết lập
                </button>
              </>
            )}
            {!setup && (
              <label className="block">
                {configured ? "Mật khẩu hiện tại" : "Tạo mật khẩu Owner"}
                <input
                  className="ml-2 rounded border bg-background px-2"
                  name="password"
                  type="password"
                  autoComplete={configured ? "current-password" : "new-password"}
                  required
                />
              </label>
            )}
            {(setup || configured) && (
              <label className="block">
                {setup ? "Mã Authenticator mới" : "Mã Authenticator hoặc mã khôi phục"}
                <input
                  className="ml-2 rounded border bg-background px-2"
                  name="code"
                  autoComplete="one-time-code"
                  required
                />
              </label>
            )}
            {mode === "password" && !setup && (
              <label className="block">
                Mật khẩu mới
                <input
                  className="ml-2 rounded border bg-background px-2"
                  name="new_password"
                  type="password"
                  autoComplete="new-password"
                  required
                />
              </label>
            )}
            <button type="submit" disabled={busy} className="rounded border px-2 py-1">
              {setup
                ? "Xác nhận 2FA"
                : mode === "setup" || mode === "totp"
                  ? "Tạo QR Authenticator"
                  : "Xác nhận"}
            </button>
          </form>
        )
      )}
    </section>
  );
}
