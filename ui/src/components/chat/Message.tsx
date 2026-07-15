import { useState } from "react";
import {
  Copy,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Check,
  User,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function UserMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-end gap-3 group">
      <div className="max-w-[75%]">
        <div className="rounded-2xl rounded-tr-sm bg-primary text-primary-foreground px-4 py-2.5 text-[14.5px] leading-relaxed shadow-sm">
          {children}
        </div>
        <div className="mt-1 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <IconBtn icon={Copy} label="Copy" />
        </div>
      </div>
      <div className="h-8 w-8 rounded-full bg-surface-3 grid place-items-center shrink-0 border border-border">
        <User className="h-4 w-4 text-muted-foreground" />
      </div>
    </div>
  );
}

export function AssistantMessage({
  children,
  agent = "Assistant",
}: {
  children: React.ReactNode;
  agent?: string;
}) {
  return (
    <div className="flex gap-3 group">
      <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary to-orange-500 grid place-items-center shrink-0 shadow-[var(--shadow-glow)]">
        <Sparkles className="h-4 w-4 text-primary-foreground" />
      </div>
      <div className="min-w-0 flex-1 max-w-[85%]">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-sm font-medium">{agent}</span>
        </div>
        <div className="text-[14.5px] leading-relaxed space-y-3 text-foreground/95">{children}</div>
        <div className="mt-2 flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
          <IconBtn icon={Copy} label="Copy" />
          <IconBtn icon={RefreshCw} label="Regenerate" />
          <IconBtn icon={ThumbsUp} label="Good" />
          <IconBtn icon={ThumbsDown} label="Bad" />
        </div>
      </div>
    </div>
  );
}

function IconBtn({ icon: Icon, label }: { icon: any; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7 text-muted-foreground hover:text-foreground"
      onClick={() => {
        if (label === "Copy") {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }
      }}
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
    <div className="flex gap-3">
      <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary to-orange-500 grid place-items-center shrink-0 opacity-70">
        <Sparkles className="h-4 w-4 text-primary-foreground animate-pulse" />
      </div>
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
          Đang suy nghĩ
        </div>
        <div className="rounded-lg border border-dashed border-border bg-surface-2/40 px-3 py-2.5 text-sm text-muted-foreground italic">
          {text || "Đang xử lý..."}
          <span className="inline-block ml-1 w-1.5 h-3.5 bg-primary/70 align-middle animate-pulse" />
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
          className="h-1.5 w-1.5 rounded-full bg-primary/80 animate-bounce"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}
