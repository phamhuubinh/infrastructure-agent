import { useState } from "react";
import {
  FileText, Braces, Info, ChevronDown,
  ChevronRight, Copy, CheckCircle2, XCircle,
  AlertCircle, Clock, X,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
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

type Session = {
  id: string;
  title: string;
  messages: { role: string; content: string; steps?: Step[] }[];
};

export function ContextPanel({ onClose, session }: { onClose?: () => void; session: Session }) {
  const lastAssistantMsg = [...session.messages].reverse().find((m) => m.role === "assistant");
  const steps = lastAssistantMsg?.steps || [];

  const intentStep = steps.find((s) => s.type === "intent");
  const evidenceStep = steps.find((s) => s.type === "evidence");
  const promptStep = steps.find((s) => s.type === "prompt");
  const assessmentStep = steps.find((s) => s.type === "assessment");

  const hasData = steps.length > 0;

  return (
    <aside className="hidden lg:flex w-[380px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between px-4 h-12 border-b border-border">
        <div className="flex items-center gap-2">
          {hasData ? (
            <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          ) : (
            <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          )}
          <span className="text-sm font-medium">Context</span>
          <span className="text-mono text-[11px] text-muted-foreground">· {session.id.slice(0, 12)}</span>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {!hasData ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center">
            <Info className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Gửi câu hỏi để xem context.</p>
          </div>
        </div>
      ) : (
        <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
          <TabsList className="mx-3 mt-3 bg-surface-2 border border-border h-9 p-1 grid grid-cols-3">
            <TabsTrigger value="overview" className="text-xs data-[state=active]:bg-surface-3"><Info className="h-3.5 w-3.5" /></TabsTrigger>
            <TabsTrigger value="json" className="text-xs data-[state=active]:bg-surface-3"><Braces className="h-3.5 w-3.5" /></TabsTrigger>
            <TabsTrigger value="logs" className="text-xs data-[state=active]:bg-surface-3"><FileText className="h-3.5 w-3.5" /></TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto p-4">
            <TabsContent value="overview" className="mt-0 space-y-3">
              {intentStep && (
                <Section title="Intent" defaultOpen>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <Meta k="Intent" v={intentStep.intent || "N/A"} />
                    <Meta k="Confidence" v={intentStep.confidence || "N/A"} />
                    <Meta k="Target" v={intentStep.target || "N/A"} />
                  </div>
                  {intentStep.matched_keywords && intentStep.matched_keywords.length > 0 && (
                    <div className="flex gap-1 flex-wrap mt-2">
                      {intentStep.matched_keywords.map((kw) => (
                        <Badge key={kw} variant="secondary" className="text-[10px]">{kw}</Badge>
                      ))}
                    </div>
                  )}
                </Section>
              )}

              {evidenceStep && (
                <Section title="Evidence" defaultOpen>
                  <div className="grid grid-cols-2 gap-2 text-sm mb-2">
                    <Meta k="Collected" v={String(evidenceStep.collected || 0)} />
                    <Meta k="Successful" v={String(evidenceStep.successful || 0)} />
                    <Meta k="Failed" v={String(evidenceStep.failed || 0)} />
                    <Meta k="Complete" v={evidenceStep.complete ? "Yes" : "No"} />
                  </div>
                  {evidenceStep.runtime_metrics && (
                    <div className="grid grid-cols-3 gap-2 text-sm mb-2">
                      <Meta k="Duration" v={`${((evidenceStep.runtime_metrics.execution_duration || 0) * 1000).toFixed(0)}ms`} />
                      <Meta k="Nodes" v={`${evidenceStep.runtime_metrics.successful_nodes}/${evidenceStep.runtime_metrics.total_nodes}`} />
                      <Meta k="Tool calls" v={String(evidenceStep.runtime_metrics.tool_calls)} />
                    </div>
                  )}
                  {evidenceStep.items && evidenceStep.items.length > 0 && (
                    <div className="space-y-1">
                      {evidenceStep.items.map((item, i) => (
                        <div key={i} className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-surface-2 text-sm">
                          {item.success
                            ? <CheckCircle2 className="h-3 w-3 text-success shrink-0" />
                            : <XCircle className="h-3 w-3 text-destructive shrink-0" />}
                          <span className="flex-1 truncate text-mono text-[12px]">{item.capability}</span>
                          <span className="text-[10px] text-muted-foreground">{item.evidence}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </Section>
              )}

              {promptStep && (
                <Section title="Prompt">
                  <Meta k="Size" v={`${(promptStep.size || 0).toLocaleString()} bytes`} />
                </Section>
              )}

              {assessmentStep && (
                <Section title="Assessment" defaultOpen>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <Meta k="Model" v={assessmentStep.model || "N/A"} />
                    <Meta k="Latency" v={assessmentStep.latency_ms ? `${(assessmentStep.latency_ms / 1000).toFixed(1)}s` : "N/A"} />
                    <Meta k="Prompt tokens" v={assessmentStep.prompt_tokens != null ? String(assessmentStep.prompt_tokens) : "N/A"} />
                    <Meta k="Completion tokens" v={assessmentStep.completion_tokens != null ? String(assessmentStep.completion_tokens) : "N/A"} />
                  </div>
                </Section>
              )}
            </TabsContent>

            <TabsContent value="json" className="mt-0">
              <div className="rounded-md border border-border bg-background overflow-hidden">
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-2">
                  <span className="text-mono text-[11px] text-muted-foreground">pipeline.json</span>
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
                <div key={i} className="grid grid-cols-[auto_1fr] gap-2 text-mono text-[11.5px] px-1 py-1 rounded hover:bg-surface-2">
                  <span className={cn(
                    "uppercase font-medium text-[10px]",
                    step.type === "intent" && "text-blue-400",
                    step.type === "evidence" && "text-amber-400",
                    step.type === "prompt" && "text-purple-400",
                    step.type === "assessment" && "text-green-400",
                  )}>{step.type}</span>
                  <span className="text-foreground/85">
                    {step.type === "intent" && `${step.intent} → ${step.target}`}
                    {step.type === "evidence" && `${step.successful}/${step.collected} items collected`}
                    {step.type === "prompt" && `${(step.size || 0).toLocaleString()} bytes`}
                    {step.type === "assessment" && `${step.model || ""} · ${step.latency_ms ? `${(step.latency_ms / 1000).toFixed(1)}s` : ""}`}
                  </span>
                </div>
              ))}
            </TabsContent>
          </div>
        </Tabs>
      )}
    </aside>
  );
}

function Section({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border bg-surface-2/40">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {title}
      </button>
      {open && (
        <>
          <Separator />
          <div className="p-3">{children}</div>
        </>
      )}
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className="text-mono text-[12.5px] truncate">{v}</div>
    </div>
  );
}
