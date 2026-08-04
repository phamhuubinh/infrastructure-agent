import { useState, useCallback } from "react";
import { Copy, RefreshCw, Check, Clock3, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { OrionIcon } from "@/components/OrionIcon";

export function UserMessage({
  children,
  content,
  askedAt,
}: {
  children: React.ReactNode;
  content?: string;
  askedAt?: string;
}) {
  const textContent = content ?? (typeof children === "string" ? children : "");
  return (
    <div className="group flex justify-end">
      <div className="max-w-[75%]">
        <div className="ml-auto w-fit rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-[14.5px] leading-relaxed text-primary-foreground shadow-sm">
          {children}
        </div>
        <div className="mt-1 flex items-center justify-end gap-2">
          {askedAt && (
            <span
              className="whitespace-nowrap text-[11px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
              title={new Date(askedAt).toLocaleString()}
            >
              {formatAskedAt(askedAt)}
            </span>
          )}
          <div className="opacity-0 transition-opacity group-hover:opacity-100">
            <IconBtn icon={Copy} label="Copy" content={textContent} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function AssistantMessage({
  children,
  agent = "Orion",
  content,
  responseTimeMs,
  onRegenerate,
  regenerateDisabled = false,
}: {
  children: React.ReactNode;
  agent?: string;
  content?: string;
  responseTimeMs?: number;
  onRegenerate?: () => void;
  regenerateDisabled?: boolean;
}) {
  const textContent = content ?? (typeof children === "string" ? children : "");
  return (
    <div className="group flex gap-2">
      <OrionIcon className="h-5 w-5 shrink-0" />
      <div className="min-w-0 flex-1 max-w-[85%]">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-sm font-medium">{agent}</span>
        </div>
        <div className="text-[14.5px] leading-relaxed space-y-3 text-foreground/95">{children}</div>
        <div className="mt-2 flex items-center gap-2">
          <div className="flex items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100">
            <IconBtn icon={Copy} label="Copy" content={textContent} />
            <IconBtn
              icon={RefreshCw}
              label="Regenerate"
              onClick={onRegenerate}
              disabled={!onRegenerate || regenerateDisabled}
            />
          </div>
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock3 className="h-3 w-3" />
            {responseTimeMs === undefined
              ? "Chưa ghi nhận thời gian"
              : `Trả lời trong ${formatResponseTime(responseTimeMs)}`}
          </span>
        </div>
      </div>
    </div>
  );
}

function formatResponseTime(milliseconds: number) {
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(
    milliseconds / 1000,
  )} giây`;
}

function formatAskedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  })
    .format(date)
    .toUpperCase();
}

function IconBtn({
  icon: Icon,
  label,
  content,
  onClick,
  disabled = false,
}: {
  icon: LucideIcon;
  label: string;
  content?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const handleClick = useCallback(() => {
    if (disabled) return;
    if (label === "Copy" && content) {
      navigator.clipboard?.writeText(content).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      });
    } else {
      onClick?.();
    }
  }, [label, content, onClick, disabled]);

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7 text-muted-foreground hover:text-foreground"
      onClick={handleClick}
      disabled={disabled}
      title={label}
      aria-label={label}
    >
      {copied && label === "Copy" ? (
        <Check className="h-3.5 w-3.5 text-success" />
      ) : (
        <Icon className="h-3.5 w-3.5" />
      )}
    </Button>
  );
}

export function Prose({ children }: { children: React.ReactNode }) {
  return <div className="[&>p]:mb-2 [&>p:last-child]:mb-0">{children}</div>;
}

export function CodeBlock({ lang = "tsx", code }: { lang?: string; code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-2">
        <span className="text-mono text-[11px] text-muted-foreground">{lang}</span>
        <button
          onClick={() => {
            navigator.clipboard?.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-success" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="p-3.5 text-mono text-[12.5px] leading-relaxed overflow-x-auto">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function ThinkingBlock({ text }: { text?: string }) {
  return (
    <div className="flex gap-2">
      <OrionIcon className="h-5 w-5 shrink-0 animate-pulse opacity-70" />
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
          Đang suy nghĩ
        </div>
        <div className="rounded-lg border border-dashed border-border bg-surface-2/40 px-3 py-2.5 text-sm text-muted-foreground italic">
          {text || "Đang xử lý..."}
          <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse bg-titanium/70 align-middle" />
        </div>
      </div>
    </div>
  );
}

export function StreamingDots() {
  return (
    <div className="flex gap-1 items-center h-5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-titanium/80"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}
