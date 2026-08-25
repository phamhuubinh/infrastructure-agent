import { Link, useRouterState } from "@tanstack/react-router";
import {
  MessageSquare,
  FolderKanban,
  Settings,
  SquarePen,
  Sun,
  Moon,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useChat } from "@/lib/chat-store";
import { OrionIcon } from "@/components/OrionIcon";

const navItems = [
  { to: "/", label: "Trò chuyện", icon: MessageSquare },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/settings", label: "Cài đặt", icon: Settings },
];

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [collapsed, setCollapsed] = useState(false);
  const { sessions, currentSessionId, startNewChat, switchSession, generatingSessions } = useChat();

  useEffect(() => {
    setCollapsed(localStorage.getItem("orion-sidebar-collapsed") === "true");
  }, []);

  function toggleSidebar() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem("orion-sidebar-collapsed", String(next));
      return next;
    });
  }

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={toggleSidebar}
        className="fixed left-3 top-3 z-40 hidden h-9 w-9 place-items-center rounded-lg border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-foreground md:grid"
        aria-label="Mở thanh bên"
        title="Mở thanh bên"
      >
        <PanelLeftOpen className="h-4 w-4" />
      </button>
    );
  }

  return (
    <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      {/* Brand */}
      <div className="p-3 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2">
          <OrionIcon className="h-7 w-7 shrink-0" />
          <div className="flex-1 min-w-0 text-left">
            <div className="truncate text-xl font-semibold leading-none">Orion</div>
          </div>
          <button
            type="button"
            onClick={toggleSidebar}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            aria-label="Thu gọn thanh bên"
            title="Thu gọn thanh bên"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* New chat */}
      <div className="p-3 border-b border-sidebar-border">
        <Button
          asChild
          variant="default"
          className="w-full justify-start gap-2 bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover active:bg-primary-active"
        >
          <Link to="/" onClick={startNewChat}>
            <SquarePen className="h-4 w-4" /> Đoạn chat mới
          </Link>
        </Button>
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
              <item.icon className={cn("h-4 w-4", active && "text-foreground")} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Conversations */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 mt-2 space-y-0.5">
        {sessions.length === 0 && (
          <div className="px-2.5 py-4 text-[11px] text-muted-foreground text-center">
            Chưa có hội thoại nào. Hãy bắt đầu một cuộc trò chuyện mới.
          </div>
        )}
        {sessions.map((s) => (
          <ChatRow
            key={s.id}
            id={s.id}
            title={s.title}
            active={s.id === currentSessionId}
            isGenerating={generatingSessions.has(s.id)}
            onSelect={() => switchSession(s.id)}
          />
        ))}
      </div>

      {/* Theme toggle */}
      <div className="p-2 border-t border-sidebar-border">
        <ThemeToggle />
      </div>
    </aside>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    const current = document.documentElement.className as "light" | "dark";
    if (current === "light" || current === "dark") setTheme(current);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.className = next;
    localStorage.setItem("theme", next);
  }

  return (
    <button
      onClick={toggle}
      className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground transition-colors cursor-pointer"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      <span>{theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}</span>
    </button>
  );
}

function ChatRow({
  id,
  title,
  active,
  isGenerating,
  onSelect,
}: {
  id: string;
  title: string;
  active: boolean;
  isGenerating: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      className={cn(
        "group w-full flex items-center gap-1 rounded-md px-1 text-sm transition-colors",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/85 hover:bg-sidebar-accent/70",
      )}
    >
      {isGenerating && <Loader2 className="ml-1 h-3.5 w-3.5 shrink-0 animate-spin text-titanium" />}
      {!isGenerating && <span className="w-4 shrink-0" />}
      <button
        onClick={() => void onSelect()}
        className="flex-1 truncate text-left px-1.5 py-1.5 cursor-pointer"
      >
        {title}
      </button>
    </div>
  );
}
