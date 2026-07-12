import { Link, useRouterState } from "@tanstack/react-router";
import {
  MessageSquare, Target, BookOpen, BarChart3, Settings,
  Search, Plus, Star, Pin, ChevronDown, Sparkles,
  Bot, Zap, Cpu, MoreHorizontal, LogOut, CreditCard, HelpCircle,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

const navItems = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/targets", label: "Targets", icon: Target },
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

const pinned = [
  { id: "p1", title: "Q4 planning brief", agent: "Strategist" },
  { id: "p2", title: "Refactor auth flow", agent: "Coder" },
];

const favorites = [
  { id: "f1", title: "Investor deck outline", agent: "Writer" },
  { id: "f2", title: "SQL migration plan", agent: "Coder" },
  { id: "f3", title: "Brand voice guide", agent: "Writer" },
];

const history = [
  { group: "Today", items: [
    { id: "h1", title: "Compare vector databases", agent: "Researcher" },
    { id: "h2", title: "Rewrite onboarding email", agent: "Writer" },
    { id: "h3", title: "Debug streaming timeout", agent: "Coder" },
  ]},
  { group: "Yesterday", items: [
    { id: "h4", title: "Weekly stand-up summary", agent: "Assistant" },
    { id: "h5", title: "Explain LoRA fine-tuning", agent: "Researcher" },
  ]},
  { group: "Previous 7 days", items: [
    { id: "h6", title: "Pricing page copy variants", agent: "Writer" },
    { id: "h7", title: "Kubernetes readiness probes", agent: "Coder" },
    { id: "h8", title: "Competitor teardown: Nova", agent: "Strategist" },
    { id: "h9", title: "Meeting notes → action items", agent: "Assistant" },
  ]},
];

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [query, setQuery] = useState("");

  return (
    <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      {/* Workspace */}
      <div className="p-3 border-b border-sidebar-border">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 hover:bg-sidebar-accent transition-colors">
              <div className="h-7 w-7 rounded-md bg-gradient-to-br from-primary to-orange-500 grid place-items-center text-primary-foreground shadow-sm">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <div className="flex-1 min-w-0 text-left">
                <div className="text-sm font-medium truncate">Northwind Labs</div>
                <div className="text-[11px] text-muted-foreground truncate">Pro workspace</div>
              </div>
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
            <DropdownMenuItem>Northwind Labs <Badge variant="secondary" className="ml-auto">Pro</Badge></DropdownMenuItem>
            <DropdownMenuItem>Personal</DropdownMenuItem>
            <DropdownMenuItem>Acme Inc.</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem><Plus className="h-4 w-4 mr-2" /> New workspace</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Agent selector + New chat */}
      <div className="p-3 space-y-2 border-b border-sidebar-border">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center gap-2 rounded-lg border border-sidebar-border bg-sidebar-accent/50 px-2.5 py-2 hover:bg-sidebar-accent transition-colors">
              <Bot className="h-4 w-4 text-primary" />
              <div className="flex-1 min-w-0 text-left">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Active agent</div>
                <div className="text-sm font-medium truncate">Atlas · Strategist</div>
              </div>
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel>Agents</DropdownMenuLabel>
            <DropdownMenuItem><Sparkles className="h-4 w-4 mr-2 text-primary" /> Atlas · Strategist</DropdownMenuItem>
            <DropdownMenuItem><Cpu className="h-4 w-4 mr-2 text-info" /> Nova · Coder</DropdownMenuItem>
            <DropdownMenuItem><Zap className="h-4 w-4 mr-2 text-warning" /> Echo · Writer</DropdownMenuItem>
            <DropdownMenuItem><Bot className="h-4 w-4 mr-2 text-success" /> Sage · Researcher</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Manage agents…</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button variant="default" className="w-full justify-start gap-2 bg-primary text-primary-foreground hover:bg-primary/90 shadow-[var(--shadow-glow)]">
          <Plus className="h-4 w-4" /> New chat
          <kbd className="ml-auto text-mono text-[10px] px-1.5 py-0.5 rounded bg-black/20">⌘K</kbd>
        </Button>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats…"
            className="h-8 pl-8 bg-sidebar-accent/40 border-sidebar-border text-sm"
          />
        </div>
      </div>

      {/* Nav */}
      <nav className="px-2 pt-3 pb-1 space-y-0.5">
        {navItems.map((item) => {
          const active = pathname === item.to || (item.to !== "/" && pathname.startsWith(item.to));
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className={cn("h-4 w-4", active && "text-primary")} />
              <span>{item.label}</span>
              {item.to === "/targets" && (
                <Badge variant="secondary" className="ml-auto h-5 px-1.5 text-[10px]">12</Badge>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Lists */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 mt-2 space-y-4">
        <ChatGroup icon={Pin} label="Pinned" items={pinned} />
        <ChatGroup icon={Star} label="Favorites" items={favorites} />
        {history.map((g) => (
          <div key={g.group}>
            <div className="px-2.5 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground/70">
              {g.group}
            </div>
            <div className="space-y-0.5">
              {g.items.map((it) => (
                <ChatRow key={it.id} title={it.title} agent={it.agent} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* User */}
      <div className="p-2 border-t border-sidebar-border">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-sidebar-accent transition-colors">
              <Avatar className="h-8 w-8">
                <AvatarFallback className="bg-gradient-to-br from-primary to-orange-500 text-primary-foreground text-xs font-semibold">
                  MR
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0 text-left">
                <div className="text-sm font-medium truncate">Maya Rowe</div>
                <div className="text-[11px] text-muted-foreground truncate">maya@northwind.co</div>
              </div>
              <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>Account</DropdownMenuLabel>
            <DropdownMenuItem><Settings className="h-4 w-4 mr-2" /> Settings</DropdownMenuItem>
            <DropdownMenuItem><CreditCard className="h-4 w-4 mr-2" /> Billing</DropdownMenuItem>
            <DropdownMenuItem><HelpCircle className="h-4 w-4 mr-2" /> Help & docs</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive"><LogOut className="h-4 w-4 mr-2" /> Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}

function ChatGroup({ icon: Icon, label, items }: { icon: any; label: string; items: { id: string; title: string; agent: string }[] }) {
  return (
    <div>
      <div className="px-2.5 pt-1 pb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/70">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <div className="space-y-0.5">
        {items.map((it) => <ChatRow key={it.id} title={it.title} agent={it.agent} />)}
      </div>
    </div>
  );
}

function ChatRow({ title, agent }: { title: string; agent: string }) {
  return (
    <button className="group w-full flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-sidebar-foreground/85 hover:bg-sidebar-accent/70 transition-colors">
      <span className="flex-1 truncate text-left">{title}</span>
      <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">{agent}</span>
    </button>
  );
}
