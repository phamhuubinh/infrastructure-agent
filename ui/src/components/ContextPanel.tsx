import { useState } from "react";
import {
  FileText, Terminal, Braces, ListTree, Info, ChevronDown,
  ChevronRight, Download, ExternalLink, Copy, CheckCircle2,
  AlertCircle, Clock, Image as ImageIcon, X,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export function ContextPanel({ onClose }: { onClose?: () => void }) {
  return (
    <aside className="hidden lg:flex w-[380px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between px-4 h-12 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          <span className="text-sm font-medium">Context</span>
          <span className="text-mono text-[11px] text-muted-foreground">· thread_a71f</span>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
        <TabsList className="mx-3 mt-3 bg-surface-2 border border-border h-9 p-1 grid grid-cols-5">
          <TabsTrigger value="overview" className="text-xs data-[state=active]:bg-surface-3"><Info className="h-3.5 w-3.5" /></TabsTrigger>
          <TabsTrigger value="files" className="text-xs data-[state=active]:bg-surface-3"><FileText className="h-3.5 w-3.5" /></TabsTrigger>
          <TabsTrigger value="json" className="text-xs data-[state=active]:bg-surface-3"><Braces className="h-3.5 w-3.5" /></TabsTrigger>
          <TabsTrigger value="terminal" className="text-xs data-[state=active]:bg-surface-3"><Terminal className="h-3.5 w-3.5" /></TabsTrigger>
          <TabsTrigger value="logs" className="text-xs data-[state=active]:bg-surface-3"><ListTree className="h-3.5 w-3.5" /></TabsTrigger>
        </TabsList>

        <div className="flex-1 overflow-y-auto p-4">
          <TabsContent value="overview" className="mt-0 space-y-3">
            <Section title="Metadata" defaultOpen>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Meta k="Thread" v="thread_a71f92e" />
                <Meta k="Model" v="atlas-opus-4" />
                <Meta k="Agent" v="Strategist" />
                <Meta k="Tokens" v="14,382 / 128k" />
                <Meta k="Started" v="Today · 10:24" />
                <Meta k="Cost" v="$0.184" />
              </div>
            </Section>

            <Section title="Sources">
              <div className="space-y-1.5">
                {[
                  { name: "Q3-strategy.pdf", size: "2.4 MB" },
                  { name: "market-notes.md", size: "18 KB" },
                  { name: "competitors.csv", size: "94 KB" },
                ].map((f) => (
                  <div key={f.name} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-surface-2 group">
                    <FileText className="h-4 w-4 text-primary shrink-0" />
                    <span className="text-sm flex-1 truncate text-mono">{f.name}</span>
                    <span className="text-[11px] text-muted-foreground">{f.size}</span>
                    <ExternalLink className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100" />
                  </div>
                ))}
              </div>
            </Section>

            <Section title="Tool calls">
              <div className="space-y-2">
                <ToolCard name="web_search" status="ok" desc="site:techcrunch.com &quot;vector db&quot;" />
                <ToolCard name="fetch_url" status="ok" desc="https://ann-benchmarks.com" />
                <ToolCard name="run_python" status="running" desc="analyze_latencies(df)" />
              </div>
            </Section>
          </TabsContent>

          <TabsContent value="files" className="mt-0 space-y-3">
            <Section title="Preview: report.md" defaultOpen>
              <div className="rounded-md border border-border bg-background p-3 text-mono text-[12px] leading-relaxed">
                <div className="text-muted-foreground"># Q4 Strategy Draft</div>
                <div>&nbsp;</div>
                <div>## Executive summary</div>
                <div className="text-muted-foreground">Growth stalled at 6.2% MoM…</div>
                <div>&nbsp;</div>
                <div>## Priorities</div>
                <div>1. Ship <span className="text-primary">vector-native search</span></div>
                <div>2. Consolidate onboarding</div>
                <div>3. Reduce cold-start latency</div>
              </div>
              <div className="mt-2 flex gap-1.5">
                <Button size="sm" variant="secondary" className="h-7 text-xs"><Copy className="h-3 w-3 mr-1" /> Copy</Button>
                <Button size="sm" variant="secondary" className="h-7 text-xs"><Download className="h-3 w-3 mr-1" /> Download</Button>
              </div>
            </Section>
            <Section title="Images">
              <div className="grid grid-cols-2 gap-2">
                {[1,2].map((i) => (
                  <div key={i} className="aspect-video rounded-md border border-border bg-gradient-to-br from-surface-2 to-surface-3 grid place-items-center">
                    <ImageIcon className="h-6 w-6 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </Section>
          </TabsContent>

          <TabsContent value="json" className="mt-0">
            <div className="rounded-md border border-border bg-background overflow-hidden">
              <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-2">
                <span className="text-mono text-[11px] text-muted-foreground">response.json</span>
                <Button variant="ghost" size="icon" className="h-6 w-6"><Copy className="h-3 w-3" /></Button>
              </div>
              <pre className="p-3 text-mono text-[11.5px] leading-relaxed overflow-x-auto">
{`{
  "id": "msg_01HZK8P4",
  "role": "assistant",
  "model": "atlas-opus-4",
  "usage": {
    "input_tokens": 8241,
    "output_tokens": 1204,
    "cache_read": 12480
  },
  "tools": [
    { "name": "web_search", "ok": true },
    { "name": "fetch_url",  "ok": true }
  ],
  "stop_reason": "end_turn"
}`}
              </pre>
            </div>
          </TabsContent>

          <TabsContent value="terminal" className="mt-0">
            <div className="rounded-md border border-border bg-black/60 overflow-hidden">
              <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border bg-surface-2">
                <div className="flex gap-1.5">
                  <div className="h-2.5 w-2.5 rounded-full bg-destructive/70" />
                  <div className="h-2.5 w-2.5 rounded-full bg-warning/70" />
                  <div className="h-2.5 w-2.5 rounded-full bg-success/70" />
                </div>
                <span className="text-mono text-[11px] text-muted-foreground ml-2">zsh — sandbox</span>
              </div>
              <div className="p-3 text-mono text-[12px] leading-relaxed">
                <div><span className="text-success">➜</span> <span className="text-info">~/project</span> npm run build</div>
                <div className="text-muted-foreground">vite v7.1.4 building for production…</div>
                <div className="text-muted-foreground">✓ 428 modules transformed.</div>
                <div className="text-success">✓ built in 2.14s</div>
                <div className="mt-1"><span className="text-success">➜</span> <span className="text-info">~/project</span> <span className="animate-pulse">▋</span></div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="logs" className="mt-0 space-y-1">
            {[
              { t: "10:24:02", lvl: "info", msg: "Thread initialized · agent=Strategist" },
              { t: "10:24:03", lvl: "info", msg: "Loaded 3 sources (2.6 MB)" },
              { t: "10:24:07", lvl: "warn", msg: "Rate limit: 82% of window used" },
              { t: "10:24:11", lvl: "info", msg: "Tool web_search returned 8 results" },
              { t: "10:24:14", lvl: "error", msg: "fetch_url: 429 from example.com — retrying" },
              { t: "10:24:16", lvl: "info", msg: "Tool run_python started (pid 4021)" },
              { t: "10:24:22", lvl: "info", msg: "Streamed 1,204 output tokens" },
            ].map((l, i) => (
              <div key={i} className="grid grid-cols-[auto_auto_1fr] gap-2 text-mono text-[11.5px] px-1 py-1 rounded hover:bg-surface-2">
                <span className="text-muted-foreground">{l.t}</span>
                <span className={cn(
                  "uppercase font-medium",
                  l.lvl === "info" && "text-info",
                  l.lvl === "warn" && "text-warning",
                  l.lvl === "error" && "text-destructive",
                )}>{l.lvl}</span>
                <span className="text-foreground/85">{l.msg}</span>
              </div>
            ))}
          </TabsContent>
        </div>
      </Tabs>
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

function ToolCard({ name, status, desc }: { name: string; status: "ok" | "running" | "error"; desc: string }) {
  const s = status === "ok" ? { i: CheckCircle2, c: "text-success" }
    : status === "running" ? { i: Clock, c: "text-warning" }
    : { i: AlertCircle, c: "text-destructive" };
  return (
    <div className="rounded-md border border-border bg-background/50 px-2.5 py-2">
      <div className="flex items-center gap-2">
        <s.i className={cn("h-3.5 w-3.5", s.c, status === "running" && "animate-spin")} />
        <span className="text-mono text-[12px] font-medium">{name}</span>
        <Badge variant="secondary" className="ml-auto h-5 text-[10px] uppercase">{status}</Badge>
      </div>
      <div className="mt-1 text-mono text-[11px] text-muted-foreground truncate">{desc}</div>
    </div>
  );
}
