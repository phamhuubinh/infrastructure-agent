import { useState, useEffect, useRef, type ComponentType } from "react";
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
  Zap,
  Wrench,
  Activity,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  type LucideIcon,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { OrionIcon } from "@/components/OrionIcon";

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

const stepLabels: Record<
  string,
  { icon: ComponentType<{ className?: string }>; label: string; color: string }
> = {
  intent: { icon: Target, label: "Intent Resolution", color: "text-blue-400" },
  evidence: { icon: Layers, label: "Evidence Collection", color: "text-amber-400" },
  prompt: { icon: FileText, label: "Prompt Assembly", color: "text-purple-400" },
  assessment: { icon: OrionIcon, label: "AI Assessment", color: "text-green-400" },
};

export function ContextPanel({ session }: { session: Session }) {
  let latestQuestion = "";
  const responses = session.messages.flatMap((message, messageIndex) => {
    if (message.role === "user") {
      latestQuestion = message.content;
      return [];
    }
    if (!message.steps?.length) return [];
    return [{ message, messageIndex, question: latestQuestion }];
  });

  const [selectedIdx, setSelectedIdx] = useState<number | null>(
    responses.length > 0 ? responses.length - 1 : null,
  );
  const [collapsed, setCollapsed] = useState(false);
  const activeResponseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setCollapsed(localStorage.getItem("orion-context-panel-collapsed") === "true");
  }, []);

  useEffect(() => {
    setSelectedIdx(responses.length > 0 ? responses.length - 1 : null);
  }, [session.id, responses.length]);

  useEffect(() => {
    activeResponseRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedIdx]);

  function togglePanel() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem("orion-context-panel-collapsed", String(next));
      return next;
    });
  }

  const current = selectedIdx != null ? responses[selectedIdx]?.message : null;
  const steps = current?.steps || [];

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
      {responses.length === 0 ? (
        <>
          <div className="flex justify-end border-b border-border p-2">
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
          <div className="flex-1 flex items-center justify-center px-4">
            <div className="text-center">
              <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-xl border border-border bg-surface-2">
                <Info className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">Chưa có dữ liệu phân tích</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Gửi câu hỏi để xem chi tiết xử lý.
              </p>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="shrink-0 border-b border-border bg-background/40 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold">Phản hồi</span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                  {responses.length}
                </span>
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
            <div className="max-h-44 space-y-1.5 overflow-y-auto pr-1">
              {responses.map(({ message, messageIndex, question }, i) => {
                const isActive = i === selectedIdx;
                const intent = message.steps?.find((step) => step.type === "intent")?.intent;
                return (
                  <button
                    key={messageIndex}
                    ref={isActive ? activeResponseRef : undefined}
                    onClick={() => setSelectedIdx(i)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-all",
                      isActive
                        ? "border-primary/30 bg-primary/10 text-foreground shadow-sm"
                        : "border-transparent text-muted-foreground hover:border-border hover:bg-surface-2 hover:text-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "grid h-7 w-7 shrink-0 place-items-center rounded-md",
                        isActive ? "bg-primary text-primary-foreground" : "bg-surface-2",
                      )}
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium">
                        {question || `Câu hỏi ${i + 1}`}
                      </span>
                      {intent && (
                        <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                          {intent.replaceAll("_", " ")}
                        </span>
                      )}
                    </span>
                    <ChevronRight
                      className={cn(
                        "h-3.5 w-3.5 shrink-0",
                        isActive ? "text-foreground" : "text-muted-foreground/50",
                      )}
                    />
                  </button>
                );
              })}
            </div>
          </div>

          <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
            <TabsList className="mx-3 mt-3 grid h-10 shrink-0 grid-cols-3 border border-border bg-surface-2 p-1">
              <TabsTrigger
                value="overview"
                className="gap-1.5 text-[11px] data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <Info className="h-3.5 w-3.5" />
                Tổng quan
              </TabsTrigger>
              <TabsTrigger
                value="json"
                className="gap-1.5 text-[11px] data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <Braces className="h-3.5 w-3.5" />
                JSON
              </TabsTrigger>
              <TabsTrigger
                value="logs"
                className="gap-1.5 text-[11px] data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                <FileText className="h-3.5 w-3.5" />
                Nhật ký
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto p-4">
              <TabsContent value="overview" className="mt-0 space-y-3">
                {steps.map((step, i) => (
                  <PipelineStepCard key={step.type + i} step={step} index={i} />
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
                    key={step.type + i}
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
  const cfg = stepLabels[step.type] || {
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
        <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface-3">
          <cfg.icon className="h-3.5 w-3.5 text-foreground" />
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
          <span className="rounded bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
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
                className="rounded bg-primary px-1.5 py-0.5 text-mono text-[11px] text-primary-foreground"
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
                <Zap className="h-3 w-3 text-foreground" />
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
  icon: LucideIcon;
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

  const stepRef = useRef(step);
  useEffect(() => {
    if (stepRef.current !== step) {
      setSelectedItem(null);
      stepRef.current = step;
    }
  }, [step]);

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
            <div key={`${item.capability}_${item.evidence}_${i}`}>
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
