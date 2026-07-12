import { createFileRoute } from "@tanstack/react-router";
import { Target, Plus, Search, Filter, MoreHorizontal, TrendingUp, Calendar, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/targets")({
  head: () => ({ meta: [{ title: "Targets — Atlas Workspace" }, { name: "description", content: "Track goals, objectives, and initiatives your agents are working toward." }] }),
  component: TargetsPage,
});

const targets = [
  { id: "T-104", title: "Reach 500 monthly active workspaces", agent: "Atlas · Strategist", progress: 68, status: "on-track", due: "Dec 31", metric: "342 / 500", tag: "Growth" },
  { id: "T-098", title: "Cut assistant p95 latency below 1.2s", agent: "Nova · Coder", progress: 82, status: "on-track", due: "Nov 20", metric: "1.34s", tag: "Performance" },
  { id: "T-091", title: "Publish 12 case studies", agent: "Echo · Writer", progress: 41, status: "at-risk", due: "Q4", metric: "5 / 12", tag: "Marketing" },
  { id: "T-087", title: "Reduce token spend per active user", agent: "Sage · Researcher", progress: 24, status: "behind", due: "Q1 '26", metric: "$1.82 → $1.20", tag: "Cost" },
  { id: "T-081", title: "Launch enterprise SSO", agent: "Nova · Coder", progress: 100, status: "done", due: "Shipped", metric: "SAML + OIDC", tag: "Platform" },
  { id: "T-079", title: "Ship agent marketplace beta", agent: "Atlas · Strategist", progress: 55, status: "on-track", due: "Jan 15", metric: "12 partners", tag: "Product" },
];

const statusStyle = {
  "on-track": { c: "text-success", i: CheckCircle2, label: "On track" },
  "at-risk": { c: "text-warning", i: Clock, label: "At risk" },
  "behind": { c: "text-destructive", i: AlertCircle, label: "Behind" },
  "done": { c: "text-muted-foreground", i: CheckCircle2, label: "Done" },
} as const;

function TargetsPage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader
        title="Targets"
        subtitle="Objectives your agents are actively working toward."
        actions={
          <>
            <Button variant="secondary" size="sm"><Filter className="h-4 w-4 mr-1.5" /> Filter</Button>
            <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90"><Plus className="h-4 w-4 mr-1.5" /> New target</Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 sm:p-8 space-y-6">
        {/* Stat strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Active", value: "12", delta: "+3", icon: Target, tone: "text-primary" },
            { label: "On track", value: "8", delta: "+2", icon: CheckCircle2, tone: "text-success" },
            { label: "At risk", value: "3", delta: "+1", icon: Clock, tone: "text-warning" },
            { label: "Avg progress", value: "62%", delta: "+8%", icon: TrendingUp, tone: "text-info" },
          ].map((s) => (
            <div key={s.label} className="surface-panel p-4">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{s.label}</span>
                <s.icon className={cn("h-4 w-4", s.tone)} />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-display text-3xl">{s.value}</span>
                <span className="text-xs text-success">{s.delta}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Search */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input placeholder="Search targets…" className="h-9 pl-8 bg-surface border-border" />
          </div>
          <div className="ml-auto flex gap-1.5">
            {["All", "Growth", "Product", "Platform", "Marketing"].map((t, i) => (
              <Button key={t} variant={i === 0 ? "secondary" : "ghost"} size="sm" className="h-8">{t}</Button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="surface-panel overflow-hidden">
          <div className="grid grid-cols-[80px_minmax(0,1fr)_180px_140px_140px_100px_40px] gap-4 px-4 py-2.5 border-b border-border bg-surface-2 text-[11px] uppercase tracking-wider text-muted-foreground">
            <span>ID</span><span>Target</span><span>Owner</span><span>Progress</span><span>Status</span><span>Due</span><span></span>
          </div>
          {targets.map((t) => {
            const s = statusStyle[t.status as keyof typeof statusStyle];
            return (
              <div key={t.id} className="grid grid-cols-[80px_minmax(0,1fr)_180px_140px_140px_100px_40px] gap-4 px-4 py-3.5 border-b border-border last:border-0 items-center hover:bg-surface-2/40 group">
                <span className="text-mono text-[12px] text-muted-foreground">{t.id}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{t.title}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <Badge variant="secondary" className="h-4 text-[10px]">{t.tag}</Badge>
                    <span className="text-mono text-[11px] text-muted-foreground">{t.metric}</span>
                  </div>
                </div>
                <span className="text-sm text-foreground/85 truncate">{t.agent}</span>
                <div>
                  <Progress value={t.progress} className="h-1.5" />
                  <div className="text-[11px] text-muted-foreground mt-1 text-mono">{t.progress}%</div>
                </div>
                <div className={cn("flex items-center gap-1.5 text-sm", s.c)}>
                  <s.i className="h-3.5 w-3.5" /> {s.label}
                </div>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" /> {t.due}
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100"><MoreHorizontal className="h-4 w-4" /></Button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
