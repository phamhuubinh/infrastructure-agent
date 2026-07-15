import { useRef } from "react";
import { ArrowUp, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function RichInput({
  onDropOver,
  onSend,
}: {
  onDropOver?: boolean;
  onSend?: (text: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (ref.current?.value.trim()) {
        onSend?.(ref.current.value);
        ref.current.value = "";
      }
    }
  }

  return (
    <div
      className={cn(
        "relative rounded-2xl border bg-surface/80 backdrop-blur transition-all",
        onDropOver
          ? "border-primary glow-ring"
          : "border-border-strong shadow-[var(--shadow-elegant)]",
      )}
    >
      <textarea
        ref={ref}
        onKeyDown={handleKeyDown}
        placeholder="Hỏi về hạ tầng…"
        rows={2}
        className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed placeholder:text-muted-foreground outline-none max-h-64"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <div className="ml-auto flex items-center gap-2">
          <kbd className="hidden sm:inline text-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-muted-foreground border border-border">
            ⏎
          </kbd>
          <Button
            size="icon"
            className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function PromptSuggestions({ onPick }: { onPick?: (s: string) => void }) {
  const suggestions = [
    { prompt: "Đánh giá sức khỏe của localhost" },
    { prompt: "Zabbix đang có vấn đề gì?" },
    { prompt: "Có service nào bị lỗi?" },
    { prompt: "Security baseline có tốt không?" },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl w-full">
      {suggestions.map((s) => (
        <button
          key={s.prompt}
          onClick={() => onPick?.(s.prompt)}
          className="w-full text-left text-sm text-foreground/85 hover:text-foreground rounded-md px-3 py-2.5 hover:bg-surface-2 transition-colors border border-border"
        >
          {s.prompt}
        </button>
      ))}
    </div>
  );
}
