import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import {
  Share2, PanelRight, ChevronDown, Sparkles,
  ChevronRight, Loader2, Send, AlertCircle, CheckCircle2,
  XCircle, Target, Layers, FileText, Braces, Zap, Clock, Wrench, Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ContextPanel } from "@/components/ContextPanel";
import { cn } from "@/lib/utils";
import { useChat, type Step, type Message } from "@/lib/chat-store";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Infrastructure Agent" },
      { name: "description", content: "Infrastructure Investigation Platform" },
    ],
  }),
  component: ChatPage,
});

const API_URL = import.meta.env.VITE_API_URL || "";

function ChatPage() {
  const chatCtx = useChat();
  const [panel, setPanel] = useState(true);
  const [drag, setDrag] = useState(false);
  const session = chatCtx.sessions.find(s => s.id === chatCtx.currentSessionId);

  return (
    <>
      <div
        className="flex-1 min-w-0 flex flex-col relative"
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); }}
      >
        <div className="h-12 border-b border-border flex items-center gap-3 px-4 shrink-0">
          <div className="min-w-0 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium truncate">
              {session?.title || "Infrastructure Agent"}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-8 w-8"><Share2 className="h-4 w-4" /></Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setPanel(!panel)}>
              <PanelRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl w-full px-4 sm:px-6 py-8">
            {session && session.messages.length <= 1 ? (
              <EmptyState />
            ) : session ? (
              <Conversation messages={session.messages} />
            ) : null}
          </div>
        </div>

        <div className="border-t border-border bg-gradient-to-b from-background/50 to-background px-4 sm:px-6 py-4">
          <div className="mx-auto max-w-3xl w-full">
            <ChatInput />
            <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Infrastructure Agent — kết quả có thể sai, hãy xác minh thông tin quan trọng.</span>
            </div>
          </div>
        </div>

        {drag && (
          <div className="absolute inset-0 pointer-events-none bg-primary/5 border-2 border-dashed border-primary/50 grid place-items-center">
            <div className="text-center">
              <div className="text-display text-3xl text-primary">Drop to attach</div>
              <div className="text-sm text-muted-foreground mt-1">PDF, images, code</div>
            </div>
          </div>
        )}
      </div>

      {panel && session && <ContextPanel onClose={() => setPanel(false)} session={session} />}
    </>
  );
}

function EmptyState() {
  const { createSession } = useChat();
  const suggestions = [
    { label: "Health", prompt: "Đánh giá sức khỏe của localhost" },
    { label: "Zabbix", prompt: "Zabbix đang có vấn đề gì?" },
    { label: "Services", prompt: "Có service nào bị lỗi?" },
    { label: "Security", prompt: "Security baseline có tốt không?" },
  ];
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center gap-6">
      <div className="relative">
        <div className="absolute inset-0 blur-2xl bg-primary/20 rounded-full" />
        <div className="relative h-14 w-14 rounded-2xl bg-gradient-to-br from-primary to-orange-500 grid place-items-center shadow-[var(--shadow-glow)]">
          <Sparkles className="h-6 w-6 text-primary-foreground" />
        </div>
      </div>
      <div>
        <h1 className="text-display text-4xl">Infrastructure Agent</h1>
        <p className="text-muted-foreground mt-1.5">Hỏi về hạ tầng của bạn.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl w-full">
        {suggestions.map((s) => (
          <button
            key={s.label}
            onClick={() => {
              const id = createSession();
              setTimeout(() => {
                document.dispatchEvent(new CustomEvent("infra-send-prompt", { detail: s.prompt }));
              }, 50);
            }}
            className="w-full text-left text-sm text-foreground/85 hover:text-foreground rounded-md px-3 py-2.5 hover:bg-surface-2 transition-colors border border-border"
          >
            {s.prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function Conversation({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="space-y-8">
      {messages.map((msg, i) => (
        <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
          <div className={cn(msg.role === "user" ? "max-w-[75%]" : "max-w-full w-full")}>
            {msg.role === "user" ? (
              <div className="rounded-2xl rounded-tr-sm bg-primary text-primary-foreground px-4 py-2.5 text-sm">
                {msg.content}
              </div>
            ) : (
              <div className="space-y-3">
                {msg.steps?.map((step, si) => (
                  <PipelineStep key={si} step={step} index={si} />
                ))}
                {msg.content && (
                  <Card className="p-4 border-border/50">
                    <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                  </Card>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

type ChatInputProps = {
  onSubmit?: (text: string) => void;
};

function ChatInput({ onSubmit: _extOnSubmit }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const { getSession, updateSession } = useChat();

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setValue(detail);
      setTimeout(() => handleSubmit(detail), 10);
    };
    document.addEventListener("infra-send-prompt", handler);
    return () => document.removeEventListener("infra-send-prompt", handler);
  }, []);

  async function handleSubmit(text?: string) {
    const question = (text ?? value).trim();
    if (!question || loading) return;

    const session = getSession();
    if (!session) return;

    if (session.title === "New chat") {
      updateSession({ title: question.length > 60 ? question.slice(0, 57) + "..." : question });
    }

    setValue("");
    setError(null);
    setPipelineStatus("Đang phân tích intent...");

    const userMsg: Message = { role: "user", content: question };
    updateSession({ messages: [...session.messages, userMsg] });
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPipelineStatus(null);

      const updated = getSession();
      if (!updated) return;

      const assistantMsg: Message = {
        role: "assistant",
        content: data.assessment || "(empty response)",
        steps: data.steps,
      };

      updateSession({ messages: [...updated.messages, assistantMsg] });
    } catch (err: any) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
      setPipelineStatus(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="relative rounded-2xl border bg-surface/80 backdrop-blur transition-all border-border-strong shadow-[var(--shadow-elegant)]">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
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
            onClick={() => handleSubmit()}
            disabled={loading || !value.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {loading && pipelineStatus && (
        <div className="absolute bottom-14 left-4 right-4">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <Loader2 className="h-3 w-3 animate-spin" />
            {pipelineStatus}
          </div>
        </div>
      )}
      {error && (
        <div className="absolute bottom-14 left-4 right-4">
          <div className="text-xs text-destructive flex items-center gap-2">
            <AlertCircle className="h-3 w-3" />
            {error}
          </div>
        </div>
      )}
    </div>
  );
}

const stepConfig: Record<string, { icon: any; label: string }> = {
  intent: { icon: Target, label: "Intent Resolution" },
  evidence: { icon: Layers, label: "Evidence Collection" },
  prompt: { icon: FileText, label: "Prompt Assembly" },
  assessment: { icon: Sparkles, label: "AI Assessment" },
  default: { icon: Activity, label: "Step" },
};

function PipelineStep({ step, index }: { step: Step; index: number }) {
  const [open, setOpen] = useState(index === 3);
  const cfg = stepConfig[step.type] || stepConfig.default;

  return (
    <Card className="border-border/40 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-muted/30 transition-colors text-left"
      >
        <div className="h-7 w-7 rounded-md bg-primary/10 grid place-items-center shrink-0">
          <cfg.icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{cfg.label}</div>
          <StepSummary step={step} />
        </div>
        <div className="flex items-center gap-1.5">
          {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-3 space-y-3">
          <StepDetail step={step} />
        </div>
      )}
    </Card>
  );
}

function StepSummary({ step }: { step: Step }) {
  switch (step.type) {
    case "intent":
      return (
        <div className="flex gap-1.5 mt-0.5 flex-wrap">
          <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">{step.intent}</span>
          {step.confidence && (
            <span className="text-[10px] text-muted-foreground">{step.confidence}</span>
          )}
          <span className="text-[10px] text-muted-foreground self-center">→ {step.target}</span>
        </div>
      );
    case "evidence":
      return (
        <div className="flex gap-2 mt-0.5 text-[11px]">
          <span className="text-green-600">{step.successful ?? 0} ok</span>
          {(step.failed ?? 0) > 0 && <span className="text-red-500">{step.failed} fail</span>}
          <span className="text-muted-foreground">{step.collected} items</span>
          <span className={step.complete ? "text-green-600" : "text-amber-500"}>
            {step.complete ? "✓" : "⚠"} {step.complete ? "complete" : "partial"}
          </span>
        </div>
      );
    case "prompt":
      return (
        <div className="text-[11px] text-muted-foreground mt-0.5">
          {step.size?.toLocaleString()} bytes
        </div>
      );
    case "assessment":
      return (
        <div className="text-[11px] mt-0.5 flex gap-2">
          <span className={step.success ? "text-green-600" : "text-red-500"}>
            {step.success ? "✓ success" : "✗ failed"}
          </span>
          {step.model && <span className="text-muted-foreground">{step.model}</span>}
          {step.latency_ms && <span className="text-muted-foreground">· {(step.latency_ms / 1000).toFixed(1)}s</span>}
        </div>
      );
    default:
      return null;
  }
}

function StepDetail({ step }: { step: Step }) {
  switch (step.type) {
    case "intent":
      return <IntentDetail step={step} />;
    case "evidence":
      return <EvidenceDetail step={step} />;
    case "prompt":
      return <PromptDetail step={step} />;
    case "assessment":
      return <AssessmentDetail step={step} />;
    default:
      return null;
  }
}

function IntentDetail({ step }: { step: Step }) {
  return (
    <div className="space-y-2 text-sm">
      <div className="grid grid-cols-3 gap-3">
        <MetaBox label="Intent" value={step.intent || "N/A"} />
        <MetaBox label="Confidence" value={step.confidence || "N/A"} />
        <MetaBox label="Target" value={step.target || "N/A"} />
      </div>
      {step.matched_keywords && step.matched_keywords.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Matched keywords</span>
          <div className="flex gap-1 mt-1 flex-wrap">
            {step.matched_keywords.map((kw) => (
              <span key={kw} className="text-[11px] bg-primary/10 text-primary px-1.5 py-0.5 rounded text-mono">{kw}</span>
            ))}
          </div>
        </div>
      )}
      {step.required_evidence && step.required_evidence.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Required evidence</span>
          <div className="mt-1 space-y-0.5">
            {step.required_evidence.map((e) => (
              <div key={e} className="flex items-center gap-1.5 text-[12px] text-mono text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> {e}
              </div>
            ))}
          </div>
        </div>
      )}
      {step.planned_capabilities && step.planned_capabilities.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Planned execution</span>
          <div className="mt-1 space-y-0.5">
            {step.planned_capabilities.map((p, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[12px] text-mono text-muted-foreground">
                <Zap className="h-3 w-3 text-primary" />
                <span>{p.capability}</span>
                <span className="text-[10px] text-muted-foreground">({p.evidence})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/30 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-[12.5px] text-mono font-medium mt-0.5 text-foreground">{value}</div>
    </div>
  );
}

function EvidenceDetail({ step }: { step: Step }) {
  const [selectedItem, setSelectedItem] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      {step.runtime_metrics && (
        <div className="grid grid-cols-5 gap-2">
          <Metric label="Duration" value={`${(step.runtime_metrics.execution_duration * 1000).toFixed(0)}ms`} icon={Clock} />
          <Metric label="Nodes" value={`${step.runtime_metrics.successful_nodes}/${step.runtime_metrics.total_nodes}`} icon={Activity} />
          <Metric label="Parallel" value={`${(step.runtime_metrics.parallel_ratio * 100).toFixed(0)}%`} icon={Layers} />
          <Metric label="Tool calls" value={String(step.runtime_metrics.tool_calls)} icon={Wrench} />
          <Metric label="Failed" value={String(step.runtime_metrics.failed_nodes)} highlight={step.runtime_metrics.failed_nodes > 0 ? "text-red-500" : undefined} icon={XCircle} />
        </div>
      )}
      {step.missing_evidence && step.missing_evidence.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-md px-3 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-amber-600">
            <AlertCircle className="h-3.5 w-3.5" />
            Missing evidence
          </div>
          <div className="flex gap-1 mt-1 flex-wrap">
            {step.missing_evidence.map((m) => (
              <span key={m} className="text-[11px] bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded text-mono">{m}</span>
            ))}
          </div>
        </div>
      )}
      {step.items && step.items.length > 0 && (
        <div className="space-y-1">
          {step.items.map((item, i) => (
            <div key={i}>
              <button
                onClick={() => setSelectedItem(selectedItem === i ? null : i)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-muted/40 transition-colors text-left"
              >
                {item.success
                  ? <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                  : <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />}
                <span className="text-mono text-[12px] flex-1 min-w-0 truncate">{item.capability}</span>
                <span className="text-[10px] text-muted-foreground">{item.evidence}</span>
                {selectedItem === i
                  ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                  : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />}
              </button>
              {selectedItem === i && (
                <div className="ml-5 pl-1 border-l-2 border-border mt-1">
                  {item.error && (
                    <div className="text-[11px] text-red-500 text-mono bg-red-500/5 rounded px-2 py-1 mb-1">
                      {item.error}
                    </div>
                  )}
                  {item.data != null && (
                    <div className="bg-muted/20 rounded-md overflow-hidden">
                      <pre className="p-2 text-mono text-[11px] leading-relaxed overflow-x-auto max-h-60 overflow-y-auto">
                        {typeof item.data === "object" ? JSON.stringify(item.data, null, 2) : String(item.data)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, icon: Icon, highlight }: { label: string; value: string; icon: any; highlight?: string }) {
  return (
    <div className="bg-muted/30 rounded-md px-2 py-1.5 text-center">
      <Icon className="h-3 w-3 mx-auto mb-0.5 text-muted-foreground" />
      <div className={cn("text-[11px] text-mono font-medium", highlight || "text-foreground")}>{value}</div>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function PromptDetail({ step }: { step: Step }) {
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <MetaBox label="Size" value={`${step.size?.toLocaleString()} bytes`} />
      </div>
      {step.preview && (
        <div className="bg-muted/20 rounded-md overflow-hidden">
          <pre className="p-2 text-mono text-[11px] leading-relaxed overflow-x-auto max-h-40 overflow-y-auto text-muted-foreground">
            {step.preview}
          </pre>
        </div>
      )}
    </div>
  );
}

function AssessmentDetail({ step }: { step: Step }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-4 gap-2">
        <MetaBox label="Model" value={step.model || "N/A"} />
        <MetaBox label="Latency" value={step.latency_ms ? `${(step.latency_ms / 1000).toFixed(1)}s` : "N/A"} />
        <MetaBox label="Prompt tokens" value={step.prompt_tokens != null ? String(step.prompt_tokens) : "N/A"} />
        <MetaBox label="Completion tokens" value={step.completion_tokens != null ? String(step.completion_tokens) : "N/A"} />
      </div>
      {step.error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2 text-[12px] text-red-600 text-mono">
          {step.error}
        </div>
      )}
    </div>
  );
}
