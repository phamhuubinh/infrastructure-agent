import { createFileRoute } from "@tanstack/react-router";
import { BarChart3, Download, TrendingUp, TrendingDown, Users, MessageSquare, Zap, DollarSign } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/analytics")({
  head: () => ({ meta: [{ title: "Analytics — Atlas Workspace" }, { name: "description", content: "Usage, latency, and cost across your agents." }] }),
  component: AnalyticsPage,
});

function AnalyticsPage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader
        title="Analytics"
        subtitle="How your workspace is being used this week."
        actions={
          <>
            <div className="flex rounded-md border border-border bg-surface p-0.5">
              {["7d", "30d", "90d", "12m"].map((r, i) => (
                <button key={r} className={cn("px-2.5 py-1 text-xs rounded", i === 1 ? "bg-surface-3 text-foreground" : "text-muted-foreground hover:text-foreground")}>{r}</button>
              ))}
            </div>
            <Button variant="secondary" size="sm"><Download className="h-4 w-4 mr-1.5" /> Export</Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 sm:p-8 space-y-6">
        {/* KPI cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { l: "Messages", v: "48,214", d: "+12.4%", up: true, i: MessageSquare },
            { l: "Active users", v: "1,284", d: "+6.1%", up: true, i: Users },
            { l: "Avg latency", v: "1.34s", d: "-8.0%", up: true, i: Zap },
            { l: "Spend", v: "$1,842", d: "+18.2%", up: false, i: DollarSign },
          ].map((k) => (
            <div key={k.l} className="surface-panel p-4">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{k.l}</span>
                <k.i className="h-4 w-4 text-primary" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-display text-3xl">{k.v}</span>
                <span className={cn("text-xs flex items-center gap-0.5", k.up ? "text-success" : "text-warning")}>
                  {k.up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />} {k.d}
                </span>
              </div>
              <Sparkline />
            </div>
          ))}
        </div>

        {/* Main chart */}
        <div className="surface-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-medium">Messages over time</h3>
              <p className="text-[11px] text-muted-foreground mt-0.5">By agent · last 30 days</p>
            </div>
            <div className="flex gap-3 text-[11px]">
              {[
                { c: "bg-primary", l: "Strategist" },
                { c: "bg-info", l: "Coder" },
                { c: "bg-success", l: "Writer" },
                { c: "bg-warning", l: "Researcher" },
              ].map((s) => (
                <div key={s.l} className="flex items-center gap-1.5"><span className={cn("h-2 w-2 rounded-sm", s.c)} />{s.l}</div>
              ))}
            </div>
          </div>
          <AreaChart />
          <div className="grid grid-cols-7 gap-2 mt-2 text-[10px] text-muted-foreground text-mono">
            {["Oct 14","Oct 17","Oct 20","Oct 23","Oct 26","Oct 29","Nov 1"].map((d) => <div key={d} className="text-center">{d}</div>)}
          </div>
        </div>

        {/* Two-col */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="surface-panel p-5 lg:col-span-2">
            <h3 className="text-sm font-medium mb-4">Top agents</h3>
            <div className="space-y-3">
              {[
                { n: "Atlas · Strategist", m: 14820, share: 92 },
                { n: "Nova · Coder", m: 12043, share: 76 },
                { n: "Echo · Writer", m: 8214, share: 54 },
                { n: "Sage · Researcher", m: 6103, share: 41 },
                { n: "Ember · Analyst", m: 3204, share: 22 },
              ].map((a) => (
                <div key={a.n} className="grid grid-cols-[180px_1fr_80px] gap-3 items-center">
                  <span className="text-sm truncate">{a.n}</span>
                  <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-primary to-orange-500 rounded-full" style={{ width: `${a.share}%` }} />
                  </div>
                  <span className="text-mono text-[12px] text-right">{a.m.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="surface-panel p-5">
            <h3 className="text-sm font-medium mb-4">Model mix</h3>
            <DonutChart />
            <div className="mt-4 space-y-1.5">
              {[
                { c: "bg-primary", l: "atlas-opus-4", p: "48%" },
                { c: "bg-info", l: "nova-sonnet", p: "31%" },
                { c: "bg-success", l: "echo-mini", p: "14%" },
                { c: "bg-warning", l: "other", p: "7%" },
              ].map((m) => (
                <div key={m.l} className="flex items-center gap-2 text-[12px]">
                  <span className={cn("h-2 w-2 rounded-sm", m.c)} />
                  <span className="flex-1 text-mono">{m.l}</span>
                  <span className="text-muted-foreground">{m.p}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="surface-panel overflow-hidden">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-medium">Recent activity</h3>
            <Badge variant="secondary" className="text-[10px]">Live</Badge>
          </div>
          <div className="grid grid-cols-[160px_minmax(0,1fr)_140px_100px_100px] gap-4 px-4 py-2 border-b border-border bg-surface-2 text-[11px] uppercase tracking-wider text-muted-foreground">
            <span>Time</span><span>Event</span><span>Agent</span><span>Tokens</span><span>Cost</span>
          </div>
          {[
            ["10:42:14", "Thread created · Compare vector DBs", "Strategist", "1,204", "$0.018"],
            ["10:41:02", "Tool call · web_search", "Strategist", "412", "$0.006"],
            ["10:38:55", "Message sent · Draft outreach", "Writer", "842", "$0.011"],
            ["10:36:11", "Thread shared with team", "Coder", "—", "—"],
            ["10:34:07", "Knowledge indexed · handbook", "System", "18,204", "$0.240"],
            ["10:31:28", "Feedback · thumbs down", "Researcher", "—", "—"],
          ].map((r, i) => (
            <div key={i} className="grid grid-cols-[160px_minmax(0,1fr)_140px_100px_100px] gap-4 px-4 py-2.5 border-b border-border last:border-0 items-center hover:bg-surface-2/40">
              <span className="text-mono text-[12px] text-muted-foreground">{r[0]}</span>
              <span className="text-sm truncate">{r[1]}</span>
              <span className="text-sm text-muted-foreground">{r[2]}</span>
              <span className="text-mono text-[12px]">{r[3]}</span>
              <span className="text-mono text-[12px] text-primary">{r[4]}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Sparkline() {
  const pts = [8, 12, 10, 14, 11, 18, 16, 22, 20, 24, 21, 28];
  const max = Math.max(...pts);
  const path = pts.map((p, i) => `${(i / (pts.length - 1)) * 100},${30 - (p / max) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="mt-2 w-full h-8 overflow-visible">
      <polyline fill="none" stroke="oklch(0.78 0.14 65)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" points={path} />
      <polygon fill="oklch(0.78 0.14 65 / 0.12)" points={`0,30 ${path} 100,30`} />
    </svg>
  );
}

function AreaChart() {
  const series = [
    { color: "oklch(0.78 0.14 65)", vals: [22, 28, 30, 26, 34, 40, 38, 44, 48, 52, 50, 58, 64, 60, 68] },
    { color: "oklch(0.72 0.12 230)", vals: [16, 18, 22, 20, 24, 26, 28, 32, 30, 34, 40, 38, 42, 48, 46] },
    { color: "oklch(0.72 0.15 155)", vals: [10, 12, 14, 12, 16, 18, 20, 22, 20, 24, 26, 28, 30, 32, 34] },
    { color: "oklch(0.78 0.15 75)", vals: [6, 8, 8, 10, 10, 12, 14, 14, 16, 16, 18, 18, 20, 22, 24] },
  ];
  const max = 80;
  return (
    <svg viewBox="0 0 300 120" className="w-full h-48">
      {[0, 25, 50, 75].map((y) => (
        <line key={y} x1="0" x2="300" y1={120 - (y / max) * 120} y2={120 - (y / max) * 120} stroke="oklch(0.28 0.008 60)" strokeDasharray="2 4" />
      ))}
      {series.map((s, si) => {
        const path = s.vals.map((v, i) => `${(i / (s.vals.length - 1)) * 300},${120 - (v / max) * 120}`).join(" ");
        return (
          <g key={si}>
            <polygon fill={s.color} opacity="0.14" points={`0,120 ${path} 300,120`} />
            <polyline fill="none" stroke={s.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" points={path} />
          </g>
        );
      })}
    </svg>
  );
}

function DonutChart() {
  const data = [
    { pct: 48, color: "oklch(0.78 0.14 65)" },
    { pct: 31, color: "oklch(0.72 0.12 230)" },
    { pct: 14, color: "oklch(0.72 0.15 155)" },
    { pct: 7, color: "oklch(0.78 0.15 75)" },
  ];
  const c = 2 * Math.PI * 40;
  let offset = 0;
  return (
    <svg viewBox="0 0 120 120" className="w-full h-40">
      <circle cx="60" cy="60" r="40" fill="none" stroke="oklch(0.24 0.008 60)" strokeWidth="14" />
      {data.map((d, i) => {
        const len = (d.pct / 100) * c;
        const el = <circle key={i} cx="60" cy="60" r="40" fill="none" stroke={d.color} strokeWidth="14"
          strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} transform="rotate(-90 60 60)" strokeLinecap="butt" />;
        offset += len;
        return el;
      })}
      <text x="60" y="58" textAnchor="middle" className="fill-foreground text-mono" fontSize="16" fontWeight="600">48%</text>
      <text x="60" y="72" textAnchor="middle" className="fill-muted-foreground" fontSize="8">opus-4</text>
    </svg>
  );
}
