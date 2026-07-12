import { createFileRoute } from "@tanstack/react-router";
import { BookOpen, Plus, Upload, Search, FileText, Globe, Database, Github, FolderOpen, MoreHorizontal, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

export const Route = createFileRoute("/knowledge")({
  head: () => ({ meta: [{ title: "Knowledge Base — Atlas Workspace" }, { name: "description", content: "Sources your agents can retrieve from." }] }),
  component: KnowledgePage,
});

const collections = [
  { name: "Product docs", count: 218, size: "42 MB", updated: "2h ago", icon: BookOpen },
  { name: "Engineering wiki", count: 1420, size: "312 MB", updated: "1d ago", icon: FolderOpen },
  { name: "Customer transcripts", count: 96, size: "18 MB", updated: "4h ago", icon: FileText },
  { name: "Competitor research", count: 54, size: "8.2 MB", updated: "3d ago", icon: Globe },
];

const sources = [
  { name: "Q4-strategy.pdf", type: "PDF", kind: "File", chunks: 128, updated: "Today · 10:24", indexed: true, tag: "Strategy" },
  { name: "engineering-handbook", type: "Notion", kind: "Sync", chunks: 3421, updated: "2h ago", indexed: true, tag: "Wiki" },
  { name: "docs.northwind.co", type: "URL", kind: "Crawl", chunks: 512, updated: "Yesterday", indexed: true, tag: "Docs" },
  { name: "atlas-org/monorepo", type: "GitHub", kind: "Repo", chunks: 8942, updated: "12m ago", indexed: false, tag: "Code" },
  { name: "support-tickets.csv", type: "CSV", kind: "File", chunks: 2145, updated: "3d ago", indexed: true, tag: "Support" },
  { name: "customer-calls-oct.zip", type: "Audio", kind: "File", chunks: 0, updated: "just now", indexed: false, tag: "Sales" },
];

const kindIcon = { File: FileText, Sync: RefreshCw, Crawl: Globe, Repo: Github } as const;

function KnowledgePage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader
        title="Knowledge base"
        subtitle="Docs, sites, and datasets your agents can retrieve from."
        actions={
          <>
            <Button variant="secondary" size="sm"><Upload className="h-4 w-4 mr-1.5" /> Upload</Button>
            <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90"><Plus className="h-4 w-4 mr-1.5" /> New source</Button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 sm:p-8 space-y-8">
        {/* Collections */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium">Collections</h2>
            <Button variant="ghost" size="sm" className="text-muted-foreground">View all</Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {collections.map((c) => (
              <div key={c.name} className="surface-panel p-4 hover:border-border-strong transition-colors cursor-pointer group">
                <div className="flex items-start justify-between">
                  <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 grid place-items-center border border-primary/20">
                    <c.icon className="h-4 w-4 text-primary" />
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100"><MoreHorizontal className="h-4 w-4" /></Button>
                </div>
                <div className="mt-3 text-sm font-medium">{c.name}</div>
                <div className="text-mono text-[11px] text-muted-foreground mt-0.5">{c.count.toLocaleString()} docs · {c.size}</div>
                <div className="text-[11px] text-muted-foreground mt-2">Updated {c.updated}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Sources */}
        <section>
          <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
            <h2 className="text-sm font-medium">All sources</h2>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input placeholder="Search sources…" className="h-8 pl-8 w-64 bg-surface border-border" />
              </div>
            </div>
          </div>

          <div className="surface-panel overflow-hidden">
            <div className="grid grid-cols-[minmax(0,1fr)_120px_120px_140px_160px_100px_40px] gap-4 px-4 py-2.5 border-b border-border bg-surface-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              <span>Source</span><span>Type</span><span>Kind</span><span>Chunks</span><span>Last update</span><span>Status</span><span></span>
            </div>
            {sources.map((s) => {
              const Icon = kindIcon[s.kind as keyof typeof kindIcon] ?? FileText;
              return (
                <div key={s.name} className="grid grid-cols-[minmax(0,1fr)_120px_120px_140px_160px_100px_40px] gap-4 px-4 py-3 border-b border-border last:border-0 items-center hover:bg-surface-2/40 group">
                  <div className="min-w-0 flex items-center gap-2.5">
                    <div className="h-7 w-7 rounded-md bg-surface-2 grid place-items-center shrink-0"><Icon className="h-3.5 w-3.5 text-primary" /></div>
                    <div className="min-w-0">
                      <div className="text-mono text-[12.5px] truncate">{s.name}</div>
                      <div className="text-[11px] text-muted-foreground">{s.tag}</div>
                    </div>
                  </div>
                  <Badge variant="secondary" className="h-5 text-[10px] w-fit">{s.type}</Badge>
                  <span className="text-sm text-muted-foreground">{s.kind}</span>
                  <span className="text-mono text-[12px]">{s.chunks.toLocaleString()}</span>
                  <span className="text-sm text-muted-foreground">{s.updated}</span>
                  <div>
                    {s.indexed ? (
                      <span className="inline-flex items-center gap-1.5 text-xs text-success">
                        <span className="h-1.5 w-1.5 rounded-full bg-success" /> Indexed
                      </span>
                    ) : (
                      <div className="w-full">
                        <Progress value={42} className="h-1" />
                        <span className="text-[10px] text-warning">Indexing</span>
                      </div>
                    )}
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100"><MoreHorizontal className="h-4 w-4" /></Button>
                </div>
              );
            })}
          </div>
        </section>

        {/* Integrations */}
        <section>
          <h2 className="text-sm font-medium mb-3">Connect a source</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: Upload, label: "Upload files", desc: "PDF, MD, DOCX, CSV, audio" },
              { icon: Globe, label: "Crawl website", desc: "Point us at a URL" },
              { icon: Github, label: "GitHub repo", desc: "Public or private" },
              { icon: Database, label: "Postgres", desc: "Read-only credentials" },
            ].map((i) => (
              <button key={i.label} className="surface-panel p-4 text-left hover:border-primary/50 transition-colors">
                <div className="h-8 w-8 rounded-md bg-surface-2 grid place-items-center mb-3"><i.icon className="h-4 w-4 text-primary" /></div>
                <div className="text-sm font-medium">{i.label}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">{i.desc}</div>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
