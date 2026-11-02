import { useState } from "react";
import {
  activeServer,
  activateServer,
  saveServerProfile,
  serverProfiles,
  removeServerProfile,
  isNativeHost,
  enrollServer,
} from "@/lib/server-profiles";

export function ServerConnections() {
  const [profiles, setProfiles] = useState(serverProfiles);
  const [name, setName] = useState("");
  const [origin, setOrigin] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const current = activeServer();
  return (
    <section aria-label="Kết nối server" className="space-y-3 rounded-lg border p-4">
      <h2 className="font-semibold">Kết nối server</h2>
      <p className="break-all text-sm">
        {current.name} · {current.origin}
      </p>
      <p className="text-sm text-muted-foreground">
        Web mở server trong đúng origin đăng nhập. Ứng dụng native dùng mã kết nối do chủ server
        cấp.
      </p>
      <ul className="space-y-2">
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
      {isNativeHost() && (
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
