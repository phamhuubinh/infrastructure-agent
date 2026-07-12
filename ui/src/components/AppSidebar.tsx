import { Link, useRouterState } from "@tanstack/react-router";
import {
  MessageSquare, Target, BookOpen, BarChart3, Settings,
  Search, Plus, Sparkles, MoreHorizontal, Trash2, Pencil,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useChat } from "@/lib/chat-store";

const navItems = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/targets", label: "Targets", icon: Target },
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [query, setQuery] = useState("");
  const { sessions, currentSessionId, createSession, switchSession } = useChat();

  const filtered = query
    ? sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase()))
    : sessions;

  return (
    <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      {/* Brand */}
      <div className="p-3 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-primary to-orange-500 grid place-items-center text-primary-foreground shadow-sm">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1 min-w-0 text-left">
            <div className="text-sm font-medium truncate">Infrastructure Agent</div>
          </div>
        </div>
      </div>

      {/* New chat + Search */}
      <div className="p-3 space-y-2 border-b border-sidebar-border">
        <Button
          variant="default"
          className="w-full justify-start gap-2 bg-primary text-primary-foreground hover:bg-primary/90 shadow-[var(--shadow-glow)]"
          onClick={() => createSession()}
        >
          <Plus className="h-4 w-4" /> New chat
        </Button>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations…"
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
            </Link>
          );
        })}
      </nav>

      {/* Conversations */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 mt-2 space-y-0.5">
        {filtered.length === 0 && (
          <div className="px-2.5 py-4 text-[11px] text-muted-foreground text-center">
            No conversations yet. Start a new chat.
          </div>
        )}
        {filtered.map((s) => (
          <ChatRow
            key={s.id}
            id={s.id}
            title={s.title}
            active={s.id === currentSessionId}
            onSelect={() => switchSession(s.id)}
          />
        ))}
      </div>

      {/* User (minimal) */}
      <div className="p-2 border-t border-sidebar-border">
        <div className="w-full flex items-center gap-2.5 rounded-lg px-2 py-2">
          <div className="flex-1 min-w-0 text-left">
            <div className="text-sm font-medium truncate">Infrastructure Agent</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function ChatRow({ id, title, active, onSelect }: { id: string; title: string; active: boolean; onSelect: () => void }) {
  const { deleteSession, renameSession } = useChat();
  const [renaming, setRenaming] = useState(false);
  const [editValue, setEditValue] = useState(title);

  function handleRename() {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== title) {
      renameSession(id, trimmed);
    }
    setRenaming(false);
  }

  return (
    <div
      className={cn(
        "group w-full flex items-center gap-1 rounded-md px-1 text-sm transition-colors cursor-pointer",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/85 hover:bg-sidebar-accent/70",
      )}
    >
      {renaming ? (
        <input
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleRename}
          onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setRenaming(false); }}
          className="flex-1 bg-transparent px-1.5 py-1.5 text-sm outline-none border border-primary/50 rounded"
          autoFocus
        />
      ) : (
        <button onClick={onSelect} className="flex-1 truncate text-left px-1.5 py-1.5">
          {title}
        </button>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="h-7 w-7 rounded-md grid place-items-center text-muted-foreground hover:text-foreground hover:bg-sidebar-accent opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuItem onClick={() => { setEditValue(title); setRenaming(true); }} className="cursor-pointer">
            <Pencil className="h-4 w-4 mr-2" /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => deleteSession(id)} className="text-destructive cursor-pointer">
            <Trash2 className="h-4 w-4 mr-2" /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
