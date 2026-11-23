import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { observeHostRefresh } from "@/lib/host-refresh";
import { apiJson } from "@/lib/api";
import { desktopAppUpdates, isManagedServer } from "@/lib/server-profiles";
import type { Schemas } from "@/lib/sdk/generated";

export function HostUpdateNotice() {
  const [version, setVersion] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    const timer = window.setTimeout(() => {
      unsubscribe = observeHostRefresh(
        async (current) => {
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
  }, []);

  if (!version || version === dismissed) return null;
  return (
    <div
      role="status"
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border bg-surface px-3 py-2 text-xs"
    >
      <span>Orion Host có bản {version}.</span>
      {desktopAppUpdates() && isManagedServer() ? (
        <Link className="underline" to="/settings">
          Xem trong Cài đặt
        </Link>
      ) : (
        <span>Cài đặt bản cập nhật trên máy Host.</span>
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
