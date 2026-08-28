import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  MessageSquare,
  FolderKanban,
  Settings,
  Sun,
  Moon,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { listProjects, type Project } from "@/lib/api";
import { sessionRoute, useChat, type Session } from "@/lib/chat-store";
import { onProjectListInvalidated } from "@/lib/project-list";
import { OrionIcon } from "@/components/OrionIcon";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";

const navItems = [
  { to: "/", label: "Trò chuyện", icon: MessageSquare },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/settings", label: "Cài đặt", icon: Settings },
];

export function splitWorkspaceSessions(sessions: Session[]) {
  return {
    chatSessions: sessions.filter((session) => session.projectId === null),
    projectSessions: sessions.filter((session) => session.projectId !== null),
  };
}

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [renameTarget, setRenameTarget] = useState<Session | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [managementError, setManagementError] = useState<string | null>(null);
  const {
    sessions,
    currentSessionId,
    startNewChat,
    switchSession,
    generatingSessions,
    renameSession,
    deleteSession,
  } = useChat();

  useEffect(() => {
    setCollapsed(localStorage.getItem("orion-sidebar-collapsed") === "true");
  }, []);

  useEffect(() => {
    let disposed = false;
    const refreshProjects = () => {
      void listProjects()
        .then((loaded) => {
          if (!disposed) setProjects(loaded);
        })
        .catch(() => {
          if (!disposed) setProjects([]);
        });
    };
    refreshProjects();
    const unsubscribe = onProjectListInvalidated(refreshProjects);
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);

  function toggleSidebar() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem("orion-sidebar-collapsed", String(next));
      return next;
    });
  }

  async function selectConversation(sessionId: string) {
    const session = await switchSession(sessionId);
    if (session) await navigate(sessionRoute(session));
  }

  async function saveRename() {
    if (!renameTarget || !renameTitle.trim()) return;
    setManagementError(null);
    try {
      await renameSession(renameTarget.id, renameTitle.trim());
      setRenameTarget(null);
    } catch (reason) {
      setManagementError(reason instanceof Error ? reason.message : "Không thể đổi tên hội thoại.");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setManagementError(null);
    try {
      await deleteSession(deleteTarget.id);
      setDeleteTarget(null);
    } catch (reason) {
      setManagementError(reason instanceof Error ? reason.message : "Không thể xóa hội thoại.");
    }
  }

  function openRename(session: Session) {
    setManagementError(null);
    setRenameTitle(session.title);
    setRenameTarget(session);
  }

  function openDelete(session: Session) {
    setManagementError(null);
    setDeleteTarget(session);
  }

  const { chatSessions, projectSessions } = splitWorkspaceSessions(sessions);

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

      {/* Nav */}
      <nav className="px-2 pt-3 pb-1 space-y-0.5">
        {navItems.map((item) => {
          const active = pathname === item.to || (item.to !== "/" && pathname.startsWith(item.to));
          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={item.to === "/" ? startNewChat : undefined}
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

      {/* Ordinary Chat conversations stay separate from Project workspaces. */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 mt-2 space-y-0.5">
        <div className="px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Gần đây
        </div>
        {chatSessions.length === 0 && (
          <div className="px-2.5 py-4 text-[11px] text-muted-foreground text-center">
            Chưa có hội thoại nào. Hãy bắt đầu một cuộc trò chuyện mới.
          </div>
        )}
        {chatSessions.map((s) => (
          <ChatRow
            key={s.id}
            id={s.id}
            title={s.title}
            active={s.id === currentSessionId}
            isGenerating={generatingSessions.has(s.id)}
            onSelect={() => selectConversation(s.id)}
            onRename={() => openRename(s)}
            onDelete={() => openDelete(s)}
          />
        ))}
        <div className="mt-4 px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Projects
        </div>
        {projects.length === 0 && (
          <div className="px-2.5 py-2 text-[11px] text-muted-foreground">Chưa có Project nào.</div>
        )}
        {projects.map((project) => {
          const active = pathname === `/projects/${project.project_id}`;
          const conversations = projectSessions.filter(
            (session) => session.projectId === project.project_id,
          );
          return (
            <div key={project.project_id} className="mb-1">
              <button
                type="button"
                onClick={() =>
                  void navigate({
                    to: "/projects/$projectId",
                    params: { projectId: project.project_id },
                  })
                }
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/85 hover:bg-sidebar-accent/70",
                )}
              >
                <FolderKanban className="h-4 w-4 shrink-0" />
                <span className="truncate">{project.name}</span>
              </button>
              {conversations.map((conversation) => (
                <ChatRow
                  key={conversation.id}
                  id={conversation.id}
                  title={conversation.title}
                  active={conversation.id === currentSessionId}
                  isGenerating={generatingSessions.has(conversation.id)}
                  nested
                  onSelect={() => selectConversation(conversation.id)}
                  onRename={() => openRename(conversation)}
                  onDelete={() => openDelete(conversation)}
                />
              ))}
            </div>
          );
        })}
      </div>

      {/* Theme toggle */}
      <div className="p-2 border-t border-sidebar-border">
        <ThemeToggle />
      </div>
      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Đổi tên hội thoại</DialogTitle>
            <DialogDescription>Đặt tên hiển thị cho hội thoại này.</DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Conversation title"
            value={renameTitle}
            onChange={(event) => setRenameTitle(event.target.value)}
            maxLength={120}
            onKeyDown={(event) => {
              if (event.key === "Enter") void saveRename();
            }}
          />
          {managementError && (
            <p role="alert" className="text-sm text-destructive">
              {managementError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameTarget(null)}>
              Hủy
            </Button>
            <Button onClick={() => void saveRename()} disabled={!renameTitle.trim()}>
              Lưu
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xóa hội thoại?</DialogTitle>
            <DialogDescription>
              Hội thoại và tài liệu chỉ thuộc hội thoại này sẽ bị xóa vĩnh viễn.
            </DialogDescription>
          </DialogHeader>
          {managementError && (
            <p role="alert" className="text-sm text-destructive">
              {managementError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()}>
              Xóa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
  nested = false,
  onSelect,
  onRename,
  onDelete,
}: {
  id: string;
  title: string;
  active: boolean;
  isGenerating: boolean;
  nested?: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group w-full flex items-center gap-1 rounded-md px-1 text-sm transition-colors",
        nested && "ml-3 w-[calc(100%-0.75rem)] text-xs",
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
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            aria-label={`Quản lý ${title}`}
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onRename}>
            <Pencil /> Đổi tên
          </DropdownMenuItem>
          <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={onDelete}>
            <Trash2 /> Xóa
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
