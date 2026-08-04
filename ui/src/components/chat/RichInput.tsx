import { useRef } from "react";
import { Send } from "lucide-react";
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
          ? "border-ring glow-ring"
          : "border-border-strong shadow-[var(--shadow-elegant)]",
      )}
    >
      <textarea
        ref={ref}
        onKeyDown={handleKeyDown}
        placeholder="Nhắn tin cho Orion"
        rows={2}
        aria-label="Chat input"
        className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed placeholder:text-muted-foreground outline-none max-h-64"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="icon"
            className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
