import { useRef, useState } from "react";
import {
  Paperclip, ArrowUp, Sparkles, Wrench, AtSign, Mic,
  Image as ImageIcon, X, FileText, Globe,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function RichInput({ onDropOver }: { onDropOver?: boolean }) {
  const [value, setValue] = useState("");
  const [attachments, setAttachments] = useState<{ name: string; size: string }[]>([
    { name: "product-brief.pdf", size: "1.2 MB" },
  ]);
  const ref = useRef<HTMLTextAreaElement>(null);

  return (
    <div className={cn(
      "relative rounded-2xl border bg-surface/80 backdrop-blur transition-all",
      onDropOver ? "border-primary glow-ring" : "border-border-strong shadow-[var(--shadow-elegant)]",
    )}>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 p-2.5 pb-0">
          {attachments.map((a, i) => (
            <div key={i} className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface-2 pl-2 pr-1 py-1">
              <FileText className="h-3.5 w-3.5 text-primary" />
              <span className="text-mono text-[11.5px] truncate max-w-[160px]">{a.name}</span>
              <span className="text-[10px] text-muted-foreground">{a.size}</span>
              <button onClick={() => setAttachments(attachments.filter((_, j) => j !== i))} className="h-4 w-4 rounded hover:bg-surface-3 grid place-items-center">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Ask anything, attach files, or @mention an agent…"
        rows={2}
        className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed placeholder:text-muted-foreground outline-none max-h-64"
      />

      <div className="flex items-center gap-1 px-2 pb-2">
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" title="Attach">
          <Paperclip className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" title="Image">
          <ImageIcon className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-muted-foreground">
          <AtSign className="h-3.5 w-3.5" /> <span className="text-xs">Mention</span>
        </Button>
        <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-muted-foreground">
          <Wrench className="h-3.5 w-3.5" /> <span className="text-xs">Tools</span>
          <Badge variant="secondary" className="h-4 px-1 text-[10px] ml-0.5">4</Badge>
        </Button>
        <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-muted-foreground">
          <Globe className="h-3.5 w-3.5" /> <span className="text-xs">Web</span>
        </Button>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground"><Mic className="h-4 w-4" /></Button>
          <kbd className="hidden sm:inline text-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-muted-foreground border border-border">⌘⏎</kbd>
          <Button size="icon" className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function PromptSuggestions({ onPick }: { onPick?: (s: string) => void }) {
  const groups = [
    { icon: Sparkles, label: "Strategize", prompts: ["Draft a Q4 GTM plan for a Series A SaaS", "Compare positioning against three competitors"] },
    { icon: Wrench, label: "Build", prompts: ["Scaffold a Postgres schema for a booking app", "Refactor this component into smaller pieces"] },
    { icon: FileText, label: "Write", prompts: ["Turn these notes into an exec summary", "Rewrite the landing hero in a warmer voice"] },
    { icon: Globe, label: "Research", prompts: ["Summarize the latest on retrieval-augmented agents", "Find and cite three benchmarks for vector DBs"] },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl w-full">
      {groups.map((g) => (
        <div key={g.label} className="rounded-xl border border-border bg-surface/60 p-3 hover:border-border-strong transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-6 w-6 rounded-md bg-surface-2 grid place-items-center">
              <g.icon className="h-3.5 w-3.5 text-primary" />
            </div>
            <span className="text-xs uppercase tracking-wider text-muted-foreground">{g.label}</span>
          </div>
          <div className="space-y-1">
            {g.prompts.map((p) => (
              <button
                key={p}
                onClick={() => onPick?.(p)}
                className="w-full text-left text-sm text-foreground/85 hover:text-foreground rounded-md px-2 py-1.5 hover:bg-surface-2 transition-colors"
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
