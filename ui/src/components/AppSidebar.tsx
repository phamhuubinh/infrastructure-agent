import { Link, useRouterState } from "@tanstack/react-router";
import {
  MessageSquare,
  BookOpen,
  Settings,
  SquarePen,
  MoreHorizontal,
  Trash2,
  Pencil,
  Sun,
  Moon,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { useChat } from "@/lib/chat-store";
import { OrionIcon } from "@/components/OrionIcon";

const navItems = [
  { to: "/", label: "Trò chuyện", icon: MessageSquare },
  { to: "/knowledge", label: "Kiến thức", icon: BookOpen },
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
  const { deleteSession, renameSession } = useChat();
  const [renaming, setRenaming] = useState(false);
  const [editValue, setEditValue] = useState(title);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const prevTitleRef = useRef(title);
  useEffect(() => {
    if (prevTitleRef.current !== title) {
      setEditValue(title);
      prevTitleRef.current = title;
    }
  }, [title]);

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
        "group w-full flex items-center gap-1 rounded-md px-1 text-sm transition-colors",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/85 hover:bg-sidebar-accent/70",
      )}
    >
      {isGenerating && <Loader2 className="ml-1 h-3.5 w-3.5 shrink-0 animate-spin text-titanium" />}
      {!isGenerating && !renaming && <span className="w-4 shrink-0" />}
      {renaming ? (
        <input
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleRename();
            if (e.key === "Escape") setRenaming(false);
          }}
          className="flex-1 rounded border border-ring bg-transparent px-1.5 py-1.5 text-sm outline-none"
          autoFocus
        />
      ) : (
        <button
          onClick={onSelect}
          className="flex-1 truncate text-left px-1.5 py-1.5 cursor-pointer"
        >
          {title}
        </button>
      )}

      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="h-7 w-7 rounded-md grid place-items-center text-muted-foreground hover:text-foreground hover:bg-sidebar-accent opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem
              onClick={() => {
                setEditValue(title);
                setRenaming(true);
              }}
              className="cursor-pointer"
            >
              <Pencil className="h-4 w-4 mr-2" /> Đổi tên
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeleteConfirmOpen(true)}
              className="text-destructive cursor-pointer"
            >
              <Trash2 className="h-4 w-4 mr-2" /> Xoá
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá hội thoại?</AlertDialogTitle>
            <AlertDialogDescription>
              Hành động này không thể hoàn tác. Hội thoại "{title}" sẽ bị xoá vĩnh viễn.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteSession(id)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Xoá
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
