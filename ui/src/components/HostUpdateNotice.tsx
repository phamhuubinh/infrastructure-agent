import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { observeHostRefresh } from "@/lib/host-refresh";
import { apiJson } from "@/lib/api";
import {
  desktopAppUpdates,
  isManagedServer,
  savedUpdateChannel,
  UPDATE_CHANNEL_CHANGED,
  type UpdateChannel,
} from "@/lib/server-profiles";
import type { Schemas } from "@/lib/sdk/generated";

export function HostUpdateNotice() {
  const updates = desktopAppUpdates();
  const [version, setVersion] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [installChannel, setInstallChannel] = useState<UpdateChannel>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [channelRevision, setChannelRevision] = useState(0);

  useEffect(() => {
    const refresh = () => {
      setVersion(null);
      setInstallChannel(undefined);
      setChannelRevision((revision) => revision + 1);
    };
    window.addEventListener(UPDATE_CHANNEL_CHANGED, refresh);
    return () => window.removeEventListener(UPDATE_CHANNEL_CHANGED, refresh);
  }, []);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    const timer = window.setTimeout(() => {
      unsubscribe = observeHostRefresh(
        async (current) => {
          if (updates) {
            const channel = savedUpdateChannel(updates.defaultChannel);
            const notice = await updates.check(channel);
            if (current()) {
              setVersion(notice.available);
              setInstallChannel(notice.can_install ? channel : undefined);
            }
            return;
          }
          const notice = await apiJson<Schemas["UpdateNotice"]>("/api/updates");
          if (current()) setVersion(notice.available_host_version ?? null);
        },
        5 * 60 * 1000,
      );
    }, 3000);
    return () => {
      window.clearTimeout(timer);
      unsubscribe?.();
    };
  }, [updates, channelRevision]);

  if (!version || version === dismissed) return null;
  return (
    <div
      role="status"
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border bg-surface px-3 py-2 text-xs"
    >
      <span>
        {updates && !isManagedServer() ? "Orion Desktop" : "Orion Host"} có bản {version}.
      </span>
      {updates && installChannel ? (
        <button
          type="button"
          disabled={busy}
          className="font-medium underline"
          onClick={() => {
            setBusy(true);
            setError("");
            void updates.install(version, installChannel).catch((reason) => {
              setError(typeof reason === "string" ? reason : "Không hoàn tất cập nhật Orion.");
              setBusy(false);
            });
          }}
        >
          {busy ? "Đang xác minh bộ cài…" : "Cập nhật ngay"}
        </button>
      ) : updates ? (
        <Link className="underline" to="/settings">
          Xem trong Cài đặt
        </Link>
      ) : (
        <span>Cài đặt bản cập nhật trên máy Host.</span>
      )}
      {error && (
        <span role="alert" className="text-destructive">
          {error}
        </span>
      )}
      <button
        type="button"
        className="ml-auto text-muted-foreground"
        onClick={() => setDismissed(version)}
      >
        Ẩn
      </button>
    </div>
  );
}
