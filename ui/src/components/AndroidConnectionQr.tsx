import { useState } from "react";
import { parseConnectionQr } from "@/lib/android-connection-qr";
import { ClientError } from "@/lib/sdk/client";
import { androidConnectionScanner, enrollAndroidQr, serverProfiles } from "@/lib/server-profiles";

export function AndroidConnectionQr() {
  const scan = androidConnectionScanner();
  const [pending, setPending] = useState<ReturnType<typeof parseConnectionQr> | null>(null);
  const [password, setPassword] = useState("");
  const [verification, setVerification] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!scan) return null;

  const name = pending
    ? (serverProfiles().find((profile) => profile.origin === pending.origin)?.name ??
      new URL(pending.origin).hostname)
    : "";

  function reset() {
    setPending(null);
    setPassword("");
    setVerification("");
    setError("");
  }

  return (
    <div className="space-y-2 rounded border p-3">
      {pending ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (busy) return;
            setError("");
            setBusy(true);
            const owner = { password, totp_code: verification.trim() };
            setPassword("");
            setVerification("");
            void enrollAndroidQr(pending.origin, name, pending.code, owner)
              .then(reset)
              .catch((cause: unknown) =>
                setError(
                  cause instanceof ClientError && cause.status === 429
                    ? "Đã vượt quá số lần thử. Chờ rồi thử lại."
                    : "Không kết nối được. Kiểm tra Tailscale, thông tin xác thực và hạn dùng của QR.",
                ),
              )
              .finally(() => setBusy(false));
          }}
        >
          <p className="break-all font-medium">Kết nối với {name}</p>
          <p className="break-all text-sm">{pending.origin}</p>
          <p className="text-sm">
            Chỉ tiếp tục nếu địa chỉ này trùng với địa chỉ trên Orion Desktop của bạn.
          </p>
          <label className="block">
            Mật khẩu Owner
            <input
              className="block w-full rounded border bg-background p-2"
              type="password"
              autoComplete="off"
              required
              maxLength={1024}
              disabled={busy}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <label className="block">
            Mã xác thực 2FA hoặc mã khôi phục
            <input
              className="block w-full rounded border bg-background p-2"
              type="password"
              autoComplete="off"
              required
              maxLength={128}
              disabled={busy}
              value={verification}
              onChange={(event) => setVerification(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="rounded border px-3 py-2" disabled={busy}>
              {busy ? "Đang kết nối…" : "Xác nhận kết nối"}
            </button>
            <button
              type="button"
              className="rounded border px-3 py-2"
              disabled={busy}
              onClick={reset}
            >
              Hủy
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="rounded border px-3 py-2"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError("");
            void scan()
              .then((raw) => {
                if (raw !== null) {
                  try {
                    setPending(parseConnectionQr(raw));
                  } catch {
                    setError("Mã này không phải QR kết nối Orion qua Tailscale.");
                  }
                }
              })
              .catch(() => setError("Không mở được trình quét. Kiểm tra quyền camera của Orion."))
              .finally(() => setBusy(false));
          }}
        >
          Quét QR
        </button>
      )}
      {error && (
        <p role="alert" className="text-sm">
          {error}
        </p>
      )}
    </div>
  );
}
