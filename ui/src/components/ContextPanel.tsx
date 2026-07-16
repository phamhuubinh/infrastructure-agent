import { useState } from "react";
import {
  FileText,
  Braces,
  Info,
  ChevronDown,
  ChevronRight,
  Copy,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Target,
  Layers,
  Sparkles,
  Zap,
  Wrench,
  Activity,
  MessageSquare,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type Step = {
  type: string;
  intent?: string;
  confidence?: string;
  target?: string;
  matched_keywords?: string[];
  required_evidence?: string[];
  optional_evidence?: string[];
  planned_capabilities?: { capability: string; evidence: string }[];
  collected?: number;
  successful?: number;
  failed?: number;
  items?: {
    capability: string;
    evidence: string;
    success: boolean;
    error?: string | null;
    data_preview?: string | null;
    data?: unknown;
  }[];
  complete?: boolean;
  missing_evidence?: string[];
  runtime_metrics?: {
    execution_duration: number;
    total_nodes: number;
    successful_nodes: number;
    failed_nodes: number;
    parallel_ratio: number;
    tool_calls: number;
  };
  size?: number;
  preview?: string;
  model?: string;
  latency_ms?: number;
  success?: boolean;
  error?: string | null;
  content?: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
};

type Message = {
  role: string;
  content: string;
  steps?: Step[];
};

type Session = {
  id: string;
  title: string;
  messages: Message[];
};

const stepLabels: Record<string, { icon: any; label: string; color: string }> = {
  intent: { icon: Target, label: "Intent Resolution", color: "text-blue-400" },
  evidence: { icon: Layers, label: "Evidence Collection", color: "text-amber-400" },
  prompt: { icon: FileText, label: "Prompt Assembly", color: "text-purple-400" },
  assessment: { icon: Sparkles, label: "AI Assessment", color: "text-green-400" },
};

export function ContextPanel({ session }: { session: Session }) {
  const assistantMsgs = session.messages.filter(
    (m) => m.role === "assistant" && m.steps && m.steps.length > 0,
  );

  const [selectedIdx, setSelectedIdx] = useState<number | null>(
    assistantMsgs.length > 0 ? assistantMsgs.length - 1 : null,
  );

  const current = selectedIdx != null ? assistantMsgs[selectedIdx] : null;
  const steps = current?.steps || [];

  return (
    <aside className="hidden lg:flex w-[380px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between px-4 h-12 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          {steps.length > 0 ? (
            <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          ) : (
            <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          )}
          <span className="text-sm font-medium">Ngữ cảnh</span>
          <span className="text-mono text-[11px] text-muted-foreground">
            · {session.id.slice(0, 12)}
          </span>
        </div>
      </div>

      {assistantMsgs.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center">
            <Info className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Gửi câu hỏi để xem chi tiết pipeline.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="px-3 pt-3 pb-1 shrink-0">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5 px-1">
              Responses ({assistantMsgs.length})
            </div>
            <ScrollArea className="max-h-[140px]">
              <div className="space-y-0.5 pr-3">
                {assistantMsgs.map((msg, i) => {
                  const isActive = i === selectedIdx;
                  const preview = msg.steps?.[0]?.intent || msg.content?.slice(0, 60);
                  return (
                    <button
                      key={i}
                      onClick={() => setSelectedIdx(i)}
                      className={cn(
                        "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
                      )}
                    >
                      <MessageSquare className="h-3 w-3 shrink-0" />
                      <span className="text-[11px] truncate flex-1">
                        {preview || `Response ${i + 1}`}
                      </span>
                      {isActive && (
                        <ChevronRight className="h-3 w-3 shrink-0" />
                      )}
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </div>

          <Separator />

          <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
            <TabsList className="mx-3 mt-3 bg-surface-2 border border-border h-9 p-1 grid grid-cols-3 shrink-0">
              <TabsTrigger value="overview" className="text-xs data-[state=active]:bg-surface-3">
                <Info className="h-3.5 w-3.5" />
              </TabsTrigger>
              <TabsTrigger value="json" className="text-xs data-[state=active]:bg-surface-3">
                <Braces className="h-3.5 w-3.5" />
              </TabsTrigger>
              <TabsTrigger value="logs" className="text-xs data-[state=active]:bg-surface-3">
                <FileText className="h-3.5 w-3.5" />
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto p-4">
              <TabsContent value="overview" className="mt-0 space-y-3">
                {steps.map((step, i) => (
                  <PipelineStepCard key={i} step={step} index={i} />
                ))}
              </TabsContent>

              <TabsContent value="json" className="mt-0">
                <div className="rounded-md border border-border bg-background overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-2">
                    <span className="text-mono text-[11px] text-muted-foreground">
                      pipeline.json
                    </span>
                    <Button variant="ghost" size="icon" className="h-6 w-6">
                      <Copy className="h-3 w-3" />
                    </Button>
                  </div>
                  <pre className="p-3 text-mono text-[11.5px] leading-relaxed overflow-x-auto">
                    {JSON.stringify(steps, null, 2)}
                  </pre>
                </div>
              </TabsContent>

              <TabsContent value="logs" className="mt-0 space-y-1">
                {steps.map((step, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[auto_1fr] gap-2 text-mono text-[11.5px] px-1 py-1 rounded hover:bg-surface-2"
                  >
                    <span
                      className={cn(
                        "uppercase font-medium text-[10px]",
                        stepLabels[step.type]?.color || "text-muted-foreground",
                      )}
                    >
                      {step.type}
                    </span>
                    <span className="text-foreground/85">
                      {step.type === "intent" && `${step.intent} → ${step.target}`}
                      {step.type === "evidence" &&
                        `${step.successful}/${step.collected} items collected`}
                      {step.type === "prompt" && `${(step.size || 0).toLocaleString()} bytes`}
                      {step.type === "assessment" &&
                        `${step.model || ""} · ${step.latency_ms ? `${(step.latency_ms / 1000).toFixed(1)}s` : ""}`}
                    </span>
                  </div>
                ))}
              </TabsContent>
            </div>
          </Tabs>
        </>
      )}
    </aside>
  );
}

function PipelineStepCard({ step, index }: { step: Step; index: number }) {
  const [open, setOpen] = useState(step.type === "assessment");
  const cfg =
    stepLabels[step.type] || {
      icon: Activity,
      label: "Step",
      color: "text-muted-foreground",
    };

  return (
    <div className="rounded-lg border border-border bg-surface-2/40 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-muted/30 transition-colors text-left"
      >
        <div className="h-7 w-7 rounded-md bg-primary/10 grid place-items-center shrink-0">
          <cfg.icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {cfg.label}
          </div>
          <StepSummary step={step} />
        </div>
        <div className="flex items-center gap-1.5">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </div>
      </button>
      {open && (
        <>
          <Separator />
          <div className="p-3 space-y-3">
            <StepDetail step={step} />
          </div>
        </>
      )}
    </div>
  );
}

function StepSummary({ step }: { step: Step }) {
  switch (step.type) {
    case "intent":
      return (
        <div className="flex gap-1.5 mt-0.5 flex-wrap">
          <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">
            {step.intent}
          </span>
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
            {step.complete ? "✓ complete" : "⚠ partial"}
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
          {step.latency_ms && (
            <span className="text-muted-foreground">· {(step.latency_ms / 1000).toFixed(1)}s</span>
          )}
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

function MetaBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/30 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-[12.5px] text-mono font-medium mt-0.5 text-foreground">{value}</div>
    </div>
  );
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
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Matched keywords
          </span>
          <div className="flex gap-1 mt-1 flex-wrap">
            {step.matched_keywords.map((kw) => (
              <span
                key={kw}
                className="text-[11px] bg-primary/10 text-primary px-1.5 py-0.5 rounded text-mono"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
      {step.required_evidence && step.required_evidence.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Required evidence
          </span>
          <div className="mt-1 space-y-0.5">
            {step.required_evidence.map((e) => (
              <div
                key={e}
                className="flex items-center gap-1.5 text-[12px] text-mono text-muted-foreground"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> {e}
              </div>
            ))}
          </div>
        </div>
      )}
      {step.planned_capabilities && step.planned_capabilities.length > 0 && (
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Planned execution
          </span>
          <div className="mt-1 space-y-0.5">
            {step.planned_capabilities.map((p, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 text-[12px] text-mono text-muted-foreground"
              >
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

function Metric({
  label,
  value,
  icon: Icon,
  highlight,
}: {
  label: string;
  value: string;
  icon: any;
  highlight?: string;
}) {
  return (
    <div className="bg-muted/30 rounded-md px-2 py-1.5 text-center">
      <Icon className="h-3 w-3 mx-auto mb-0.5 text-muted-foreground" />
      <div className={cn("text-[11px] text-mono font-medium", highlight || "text-foreground")}>
        {value}
      </div>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function EvidenceDetail({ step }: { step: Step }) {
  const [selectedItem, setSelectedItem] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      {step.runtime_metrics && (
        <div className="grid grid-cols-5 gap-2">
          <Metric
            label="Duration"
            value={`${(step.runtime_metrics.execution_duration * 1000).toFixed(0)}ms`}
            icon={Clock}
          />
          <Metric
            label="Nodes"
            value={`${step.runtime_metrics.successful_nodes}/${step.runtime_metrics.total_nodes}`}
            icon={Activity}
          />
          <Metric
            label="Parallel"
            value={`${(step.runtime_metrics.parallel_ratio * 100).toFixed(0)}%`}
            icon={Layers}
          />
          <Metric
            label="Tool calls"
            value={String(step.runtime_metrics.tool_calls)}
            icon={Wrench}
          />
          <Metric
            label="Failed"
            value={String(step.runtime_metrics.failed_nodes)}
            highlight={step.runtime_metrics.failed_nodes > 0 ? "text-red-500" : undefined}
            icon={XCircle}
          />
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
              <span
                key={m}
                className="text-[11px] bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded text-mono"
              >
                {m}
              </span>
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
                {item.success ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                )}
                <span className="text-mono text-[12px] flex-1 min-w-0 truncate">
                  {item.capability}
                </span>
                <span className="text-[10px] text-muted-foreground">{item.evidence}</span>
                {selectedItem === i ? (
                  <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                )}
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
                        {typeof item.data === "object"
                          ? JSON.stringify(item.data, null, 2)
                          : String(item.data)}
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
        <MetaBox
          label="Latency"
          value={step.latency_ms ? `${(step.latency_ms / 1000).toFixed(1)}s` : "N/A"}
        />
        <MetaBox
          label="Prompt tokens"
          value={step.prompt_tokens != null ? String(step.prompt_tokens) : "N/A"}
        />
        <MetaBox
          label="Completion tokens"
          value={step.completion_tokens != null ? String(step.completion_tokens) : "N/A"}
        />
      </div>
      {step.error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2 text-[12px] text-red-600 text-mono">
          {step.error}
        </div>
      )}
    </div>
  );
}
