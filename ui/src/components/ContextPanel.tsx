import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  Info,
  PanelRightClose,
  PanelRightOpen,
  Wrench,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { Session, SourceReference, ToolActivity } from "@/lib/chat-store";

function activityLabel(activity: ToolActivity) {
  if (activity.status === "started") return "Đang chạy";
  if (activity.status === "completed") return "Hoàn tất";
  return activity.toolName.startsWith("knowledge.")
    ? "Tra cứu tài liệu thất bại"
    : "Công cụ thất bại";
}

export function ContextPanel({
  session,
  selectedSourceRefId,
  onOpenSource,
}: {
  session: Session;
  selectedSourceRefId: string | null;
  onOpenSource: (sourceRefId: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [openCallId, setOpenCallId] = useState<string | null>(null);
  const selectedSource = session.sources.find(
    (source) => source.sourceRefId === selectedSourceRefId,
  );

  useEffect(() => {
    setCollapsed(localStorage.getItem("orion-context-panel-collapsed") === "true");
  }, []);

  function togglePanel() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem("orion-context-panel-collapsed", String(next));
      return next;
    });
  }

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={togglePanel}
        className="fixed right-3 top-3 z-40 hidden h-9 w-9 place-items-center rounded-lg border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-foreground lg:grid"
        aria-label="Mở bảng chi tiết"
        title="Mở bảng chi tiết"
      >
        <PanelRightOpen className="h-4 w-4" />
      </button>
    );
  }

  return (
    <aside className="hidden w-[400px] shrink-0 flex-col border-l border-border bg-surface lg:flex">
      <div className="flex items-center justify-between border-b border-border bg-background/40 p-3">
        <div>
          <div className="text-xs font-semibold">Hoạt động runtime</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            {session.activity.length ? "Công cụ do model gọi" : "Chưa có hoạt động công cụ"}
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={togglePanel}
          className="h-8 w-8 text-muted-foreground"
          aria-label="Đóng bảng chi tiết"
          title="Đóng bảng chi tiết"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      {(selectedSource || session.documents.length > 0) && (
        <div className="border-b border-border p-3">
          <div className="mb-2 text-xs font-semibold">Nguồn phiên chat</div>
          {selectedSource && (
            <SourceCard
              source={selectedSource}
              selected
              onClick={() => onOpenSource(selectedSource.sourceRefId)}
            />
          )}
          <div className="space-y-1.5">
            {session.documents.map((document) => (
              <div
                key={document.document.document_id}
                className="flex items-center gap-2 rounded-md bg-surface-2/50 px-2 py-1.5 text-xs"
              >
                <FileText className="h-3.5 w-3.5 shrink-0 text-titanium" />
                <span className="min-w-0 flex-1 truncate">{document.document.name}</span>
                <span
                  className={
                    document.status === "ready"
                      ? "text-success"
                      : document.status === "failed"
                        ? "text-destructive"
                        : "text-amber-400"
                  }
                >
                  {document.status}
                </span>
              </div>
            ))}
          </div>
          {session.sources.length > 0 && !selectedSource && (
            <div className="mt-2 space-y-1.5">
              {session.sources.map((source) => (
                <SourceCard
                  key={source.sourceRefId}
                  source={source}
                  onClick={() => onOpenSource(source.sourceRefId)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {session.activity.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-4">
          <div className="text-center">
            <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-xl border border-border bg-surface-2">
              <Info className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium">Không có hoạt động công cụ</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Khi model dùng công cụ, trạng thái công khai sẽ hiện ở đây.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {session.activity.map((activity, index) => {
            const open = openCallId === activity.callId + "-" + index;
            const failed = activity.status === "failed";
            const completed = activity.status === "completed";
            return (
              <div
                key={activity.callId + "-" + index}
                className="overflow-hidden rounded-lg border border-border bg-surface-2/40"
              >
                <button
                  type="button"
                  onClick={() => setOpenCallId(open ? null : activity.callId + "-" + index)}
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-muted/30"
                >
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface-3">
                    {completed ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                    ) : failed ? (
                      <XCircle className="h-3.5 w-3.5 text-destructive" />
                    ) : (
                      <Wrench className="h-3.5 w-3.5 text-amber-400" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12px] font-medium">{activity.toolName}</div>
                    <div
                      className={cn(
                        "mt-0.5 text-[10px]",
                        completed ? "text-success" : failed ? "text-destructive" : "text-amber-400",
                      )}
                    >
                      {activityLabel(activity)}
                    </div>
                  </div>
                  {open ? (
                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                </button>
                {open && (
                  <>
                    <Separator />
                    <div className="p-3 text-xs text-muted-foreground">
                      Call ID: <span className="font-mono text-foreground">{activity.callId}</span>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </aside>
  );
}

function SourceCard({
  source,
  selected = false,
  onClick,
}: {
  source: SourceReference;
  selected?: boolean;
  onClick: () => void;
}) {
  const location = [
    source.url
      ? (() => {
          try {
            return new URL(source.url).hostname;
          } catch {
            return null;
          }
        })()
      : null,
    source.page === null ? null : `Trang ${source.page}`,
    source.section,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" · ");
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left text-xs transition-colors hover:bg-accent",
        selected ? "border-titanium bg-titanium/10" : "border-border bg-surface-2/50",
      )}
      aria-label={`Open source ${source.label}`}
    >
      <FileText className="h-3.5 w-3.5 shrink-0 text-titanium" />
      <span className="min-w-0 flex-1 truncate font-medium">{source.label}</span>
      {location && <span className="shrink-0 text-muted-foreground">{location}</span>}
    </button>
  );
}
