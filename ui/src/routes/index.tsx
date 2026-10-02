import { parseSseEvents } from "@/lib/chat-stream";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  AlertCircle,
  ArrowDown,
  Check,
  ChevronDown,
  FileText,
  LockKeyhole,
  Hand,
  Zap,
  Loader2,
  Paperclip,
  Send,
  Square,
  Trash2,
  XCircle,
} from "lucide-react";
import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";

import { ContextPanel } from "@/components/ContextPanel";
import { OrionIcon } from "@/components/OrionIcon";
import { AssistantMessage, UserMessage } from "@/components/chat/Message";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import {
  apiErrorMessage,
  apiFetch,
  attachProjectDocument,
  attachSessionDocument,
  deleteProjectDocument,
  type DocumentStatus,
  type MutationMode,
  type Project,
  resolveToolAuthorization,
} from "@/lib/api";
import {
  useChat,
  sessionFromTimeline,
  type Message,
  type Session,
  type SessionDocument,
  type SourceReference,
  type TimelineItem,
} from "@/lib/chat-store";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Orion" },
      { name: "description", content: "Orion — Infrastructure Investigation Platform" },
    ],
  }),
  component: ChatPage,
});

type ModelInfo = {
  model_config_id: string;
  provider_type: string;
  base_url: string;
  model_id: string;
  is_active: boolean;
};

type Generation = {
  controller: AbortController;
  requestId: string | null;
  sessionId: string | null;
  cancelled: boolean;
};

type PendingAuthorization = {
  sessionId: string;
  requestId: string;
  callId: string;
  toolName: string;
  targetRef: string;
  summary: Record<string, string>;
};

export { parseSseEvents } from "@/lib/chat-stream";

type ChatPageProps =
  | {
      project: Project;
      projectDocuments: DocumentStatus[];
      setProjectDocuments: Dispatch<SetStateAction<DocumentStatus[]>>;
    }
  | { project?: undefined; projectDocuments?: undefined; setProjectDocuments?: undefined };

function sessionDocument(status: DocumentStatus): SessionDocument {
  return {
    document: status.document,
    attachmentId: status.attachment_id,
    status: status.status,
    errorMessage: status.error_message,
    ingestion: status.ingestion || [],
  };
}

export function ChatPage({ project, projectDocuments, setProjectDocuments }: ChatPageProps) {
  const chat = useChat();
  const navigate = useNavigate();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [selectedSourceRefId, setSelectedSourceRefId] = useState<string | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const followMessagesRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const lastDisplayedSessionIdRef = useRef<string | null>(null);
  const loadedInitialScope = useRef<string | null>(null);
  const session = chat.sessions.find(
    (item) =>
      item.id === chat.currentSessionId &&
      (project ? item.projectId === project.project_id : !item.projectId),
  );
  const projectDocs = (projectDocuments || [])
    .filter((document) => !document.deleted)
    .map(sessionDocument);
  const displayedSession =
    project && session
      ? (() => {
          const documents = [
            ...new Map(
              [
                ...session.documents.filter(
                  (document) => document.document.source.kind !== "project",
                ),
                ...projectDocs,
              ].map((document) => [document.document.document_id, document]),
            ).values(),
          ];
          const projected = sessionFromTimeline(
            session.id,
            session.timeline,
            documents,
            session.projectId,
          );
          const projectedMessages = new Map(
            projected.messages.map((message) => [message.itemId, message]),
          );
          return {
            ...session,
            documents,
            sources: projected.sources,
            messages: session.messages.map((message) => {
              const canonical = projectedMessages.get(message.itemId);
              return canonical
                ? { ...message, citationSourceRefIds: canonical.citationSourceRefIds }
                : message;
            }),
          };
        })()
      : session;

  const displayedSessionId = displayedSession?.id ?? null;
  const displayedMessages = displayedSession?.messages;

  useEffect(() => {
    const scrollArea = scrollAreaRef.current;
    if (!scrollArea) return;
    if (lastDisplayedSessionIdRef.current !== displayedSessionId) {
      lastDisplayedSessionIdRef.current = displayedSessionId;
      followMessagesRef.current = true;
    }
    if (followMessagesRef.current) scrollArea.scrollTop = scrollArea.scrollHeight;
    lastScrollTopRef.current = scrollArea.scrollTop;
  }, [displayedSessionId, displayedMessages]);

  useEffect(() => {
    let disposed = false;
    void apiFetch("/api/models")
      .then(async (response) => (response.ok ? ((await response.json()) as ModelInfo[]) : []))
      .then((configured) => {
        if (!disposed) setModels(configured);
      })
      .catch(() => {
        if (!disposed) setModels([]);
      })
      .finally(() => {
        if (!disposed) setLoadingModels(false);
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!loadingModels && !models.some((model) => model.is_active)) {
      void navigate({ to: "/settings", replace: true });
    }
  }, [loadingModels, models, navigate]);

  useEffect(() => {
    const scope = project?.project_id ?? "chat";
    if (!chat.sessionsLoaded || loadedInitialScope.current === scope) return;
    loadedInitialScope.current = scope;
    const current = chat.sessions.find((item) => item.id === chat.currentSessionId);
    const candidate =
      current && (project ? current.projectId === project.project_id : current.projectId === null)
        ? current
        : chat.sessions.find((item) =>
            project ? item.projectId === project.project_id : item.projectId === null,
          );
    if (!candidate) return;
    void chat.switchSession(candidate.id);
  }, [chat, project]);

  const handleConversationScroll = useCallback(() => {
    const element = scrollAreaRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    const awayFromBottom = distanceFromBottom > 140;
    if (distanceFromBottom <= 2) followMessagesRef.current = true;
    else if (element.scrollTop < lastScrollTopRef.current) followMessagesRef.current = false;
    lastScrollTopRef.current = element.scrollTop;
    setShowScrollToBottom(awayFromBottom);
  }, []);

  return (
    <>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col relative">
        <div
          ref={scrollAreaRef}
          onScroll={handleConversationScroll}
          onWheel={(event) => {
            if (event.deltaY < 0) followMessagesRef.current = false;
          }}
          data-testid="conversation-scroll-area"
          className="min-h-0 flex-1 overflow-y-auto"
        >
          <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
            {!displayedSession || displayedSession.messages.length === 0 ? (
              <EmptyState />
            ) : (
              <Conversation
                messages={displayedSession.messages}
                generating={chat.generatingSessions.has(displayedSession.id)}
                sources={displayedSession.sources}
                onOpenSource={setSelectedSourceRefId}
              />
            )}
          </div>
        </div>
        <div className="relative border-t border-border bg-gradient-to-b from-background/50 to-background px-4 py-4 sm:px-6 lg:px-8">
          {showScrollToBottom && (
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => {
                followMessagesRef.current = true;
                scrollAreaRef.current?.scrollTo({
                  top: scrollAreaRef.current.scrollHeight,
                  behavior: "smooth",
                });
              }}
              className="absolute -top-12 left-1/2 z-20 h-9 w-9 -translate-x-1/2 rounded-full bg-background shadow-lg"
              aria-label="Đi đến cuối cuộc trò chuyện"
            >
              <ArrowDown className="h-4 w-4" />
            </Button>
          )}
          <div className="mx-auto w-full max-w-6xl">
            <ChatInput
              models={models}
              loadingModels={loadingModels}
              projectId={project?.project_id}
              projectDocuments={projectDocs}
              setProjectDocuments={setProjectDocuments}
            />
            <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Orion — kết quả có thể sai, hãy xác minh thông tin quan trọng.</span>
            </div>
          </div>
        </div>
      </div>
      {displayedSession && (
        <ContextPanel
          session={displayedSession}
          selectedSourceRefId={selectedSourceRefId}
          onOpenSource={setSelectedSourceRefId}
        />
      )}
    </>
  );
}

function EmptyState() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center gap-6">
      <OrionIcon className="relative h-14 w-14" />
      <h1 className="text-display text-4xl">Orion</h1>
    </div>
  );
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-2">
      <span className="text-sm font-medium text-muted-foreground">Orion</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-titanium/70"
            style={{ animationDelay: String(index * 150) + "ms" }}
          />
        ))}
      </span>
    </div>
  );
}

function Conversation({
  messages,
  generating,
  sources,
  onOpenSource,
}: {
  messages: Message[];
  generating: boolean;
  sources: SourceReference[];
  onOpenSource: (sourceRefId: string) => void;
}) {
  return (
    <div className="space-y-8">
      {messages.map((message) => (
        <div key={message.itemId}>
          {message.role === "user" ? (
            <UserMessage content={message.content} askedAt={message.askedAt}>
              {message.content}
            </UserMessage>
          ) : message.content.trim() ? (
            <AssistantMessage
              agent="Orion"
              content={message.content}
              responseTimeMs={message.responseTimeMs}
              inputTokens={message.inputTokens}
              outputTokens={message.outputTokens}
            >
              <Card className="p-4 border-border/50">
                <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:bg-surface-2 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-mono [&_code]:text-[12.5px] [&_p]:leading-relaxed [&_p]:text-foreground/95">
                  <AssistantMarkdown>{displayAssistantContent(message.content)}</AssistantMarkdown>
                </div>
              </Card>
              <CitationCards
                sourceRefIds={message.citationSourceRefIds || []}
                sources={sources}
                onOpenSource={onOpenSource}
              />
            </AssistantMessage>
          ) : (
            <ThinkingDots />
          )}
        </div>
      ))}
      {generating && messages.at(-1)?.content.trim() !== "" && <ThinkingDots />}
    </div>
  );
}

function displayAssistantContent(content: string) {
  return content.replace(/\s*\[\[source:[^\]\s]+\]\]/g, "");
}

function CitationCards({
  sourceRefIds,
  sources,
  onOpenSource,
}: {
  sourceRefIds: string[];
  sources: SourceReference[];
  onOpenSource: (sourceRefId: string) => void;
}) {
  const byId = new Map(sources.map((source) => [source.sourceRefId, source]));
  const seen = new Set<string>();
  const cited = sourceRefIds.flatMap((sourceRefId) => {
    if (seen.has(sourceRefId)) return [];
    const source = byId.get(sourceRefId);
    if (!source) return [];
    seen.add(sourceRefId);
    return [source];
  });
  if (cited.length === 0) return null;
  return (
    <div className="space-y-1.5" aria-label="Grounded sources">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Nguồn
      </div>
      <div className="flex flex-wrap gap-2">
        {cited.map((source) => (
          <button
            key={source.sourceRefId}
            type="button"
            onClick={() => onOpenSource(source.sourceRefId)}
            className="flex max-w-full items-center gap-1.5 rounded-md border border-border bg-surface-2/70 px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent"
            aria-label={`Open source ${source.label}`}
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-titanium" />
            <span className="truncate">{source.label}</span>
            <SourceLocation source={source} />
          </button>
        ))}
      </div>
    </div>
  );
}

export function SourceLocation({ source }: { source: SourceReference }) {
  if (source.url) {
    try {
      return <span className="truncate text-muted-foreground">{new URL(source.url).hostname}</span>;
    } catch {
      return null;
    }
  }
  const details = [source.page === null ? null : `p. ${source.page}`, source.section]
    .filter((value): value is string => Boolean(value))
    .join(" · ");
  return details ? <span className="shrink-0 text-muted-foreground">{details}</span> : null;
}

function ModelStatus({ models, loading }: { models: ModelInfo[]; loading: boolean }) {
  const navigate = useNavigate();
  const model = models.find((item) => item.is_active);
  return (
    <button
      type="button"
      onClick={() => {
        void navigate({ to: "/settings" });
      }}
      className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-foreground"
      title={model ? model.model_id + " (" + model.provider_type + ")" : "Chưa cấu hình model"}
    >
      {loading ? (
        <Loader2 className="h-3 w-3 animate-spin text-titanium" />
      ) : (
        <span
          className={
            "inline-block h-1.5 w-1.5 rounded-full " + (model ? "bg-success" : "bg-destructive")
          }
        />
      )}
      <span className="max-w-[140px] truncate">{model?.model_id || "Configure model"}</span>
    </button>
  );
}

function ChatInput({
  models,
  loadingModels,
  projectId,
  projectDocuments: activeProjectDocuments,
  setProjectDocuments,
}: {
  models: ModelInfo[];
  loadingModels: boolean;
  projectId?: string;
  projectDocuments: Session["documents"];
  setProjectDocuments?: Dispatch<SetStateAction<DocumentStatus[]>>;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [autoWarning, setAutoWarning] = useState(false);
  const [changingMode, setChangingMode] = useState(false);
  const [pendingAuthorization, setPendingAuthorization] = useState<PendingAuthorization | null>(
    null,
  );
  const [resolvingAuthorization, setResolvingAuthorization] = useState(false);
  const generation = useRef<Generation | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => () => generation.current?.controller.abort(), []);
  const {
    currentSessionId,
    sessions,
    createSession,
    setMutationMode,
    addOptimisticMessage,
    reconcileAssistantMessage,
    loadSession,
    recordEvent,
    setSessionGenerating,
    deleteDocument,
  } = useChat();
  const session = sessions.find(
    (item) =>
      item.id === currentSessionId && (projectId ? item.projectId === projectId : !item.projectId),
  );

  useEffect(() => setAutoWarning(false), [currentSessionId, projectId]);

  const mutationMode = session?.mutationMode ?? "read_only";
  const activePending =
    pendingAuthorization?.sessionId === session?.id ? pendingAuthorization : null;

  const changeMode = useCallback(
    async (mode: MutationMode) => {
      if (mode === mutationMode || changingMode || generation.current) return;
      if (mode === "auto") {
        setAutoWarning(true);
        return;
      }
      setChangingMode(true);
      setError(null);
      try {
        const sessionId = session?.id ?? (await createSession(projectId));
        await setMutationMode(sessionId, mode);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Không thể đổi quyền sửa.");
      } finally {
        setChangingMode(false);
      }
    },
    [changingMode, createSession, mutationMode, projectId, session?.id, setMutationMode],
  );

  const resolveAuthorization = useCallback(
    async (decision: "allow" | "deny") => {
      const pending = activePending;
      if (!pending || resolvingAuthorization) return;
      setResolvingAuthorization(true);
      try {
        await resolveToolAuthorization(
          pending.sessionId,
          pending.requestId,
          pending.callId,
          decision,
        );
        setPendingAuthorization(null);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Không thể quyết định thao tác.");
      } finally {
        setResolvingAuthorization(false);
      }
    },
    [activePending, resolvingAuthorization],
  );

  const attachFile = useCallback(
    async (file: File) => {
      setAttachmentError(null);
      setUploading(true);
      try {
        if (projectId) {
          const uploaded = await attachProjectDocument(projectId, file);
          setProjectDocuments?.((current) => [
            ...current.filter(
              (document) => document.document.document_id !== uploaded.document.document_id,
            ),
            { ...uploaded, ingestion: [], deleted: false },
          ]);
        } else {
          let sessionId = currentSessionId;
          if (!sessionId) sessionId = await createSession();
          await attachSessionDocument(sessionId, file);
          await loadSession(sessionId);
        }
      } catch (attachmentFailure) {
        setAttachmentError(
          attachmentFailure instanceof Error
            ? `Tải lên tài liệu thất bại: ${attachmentFailure.message}`
            : "Tải lên tài liệu thất bại.",
        );
      } finally {
        setUploading(false);
        if (fileInput.current) fileInput.current.value = "";
      }
    },
    [createSession, currentSessionId, loadSession, projectId, setProjectDocuments],
  );

  const submit = useCallback(async () => {
    const content = value.trim();
    if (!content || generation.current) return;
    setError(null);
    let sessionId = session?.id || null;
    const controller = new AbortController();
    const current: Generation = { controller, requestId: null, sessionId, cancelled: false };
    generation.current = current;
    try {
      if (!sessionId) sessionId = await createSession(projectId);
      current.sessionId = sessionId;
      addOptimisticMessage(sessionId, content);
      setValue("");
      setSessionGenerating(sessionId, true);
      const response = await apiFetch(
        "/api/sessions/" + encodeURIComponent(sessionId) + "/messages/stream",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        },
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      if (!response.body) throw new Error("Orion did not return an event stream.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let requestFailure: string | null = null;
      while (true) {
        const { done, value: chunk } = await reader.read();
        buffer += decoder.decode(chunk || new Uint8Array(), { stream: !done });
        const parsed = parseSseEvents(buffer);
        buffer = parsed.remainder;
        for (const event of parsed.events) {
          if (event.type === "request.accepted" && typeof event.payload.request_id === "string") {
            current.requestId = event.payload.request_id;
          }
          if (event.type === "request.failed") {
            requestFailure =
              typeof event.payload.message === "string"
                ? event.payload.message
                : "Yêu cầu thất bại.";
          }
          if (event.type === "tool.authorization_required" && current.requestId) {
            const { call_id, tool_name, target_ref, summary } = event.payload;
            if (
              typeof call_id === "string" &&
              typeof tool_name === "string" &&
              typeof target_ref === "string"
            ) {
              setPendingAuthorization({
                sessionId,
                requestId: current.requestId,
                callId: call_id,
                toolName: tool_name,
                targetRef: target_ref,
                summary:
                  summary && typeof summary === "object" ? (summary as Record<string, string>) : {},
              });
            }
          }
          if (event.type === "assistant.message") {
            const item = event.payload.item;
            if (
              item &&
              typeof item === "object" &&
              "item_id" in item &&
              "kind" in item &&
              "payload" in item
            ) {
              reconcileAssistantMessage(sessionId, item as TimelineItem);
            }
          }
          recordEvent(sessionId, event);
        }
        if (done) break;
      }
      await loadSession(sessionId);
      if (requestFailure) setError(requestFailure);
      if (current.cancelled) setError("Yêu cầu đã được hủy.");
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") {
        setError("Yêu cầu đã được hủy.");
      } else {
        setError(requestError instanceof Error ? requestError.message : "Yêu cầu thất bại.");
      }
      if (sessionId) {
        try {
          await loadSession(sessionId);
        } catch {
          // Keep the original request failure as the visible error.
        }
      }
    } finally {
      setPendingAuthorization((pending) => (pending?.sessionId === sessionId ? null : pending));
      if (sessionId) setSessionGenerating(sessionId, false);
      generation.current = null;
    }
  }, [
    addOptimisticMessage,
    createSession,
    loadSession,
    recordEvent,
    reconcileAssistantMessage,
    setSessionGenerating,
    session?.id,
    projectId,
    value,
  ]);

  const stop = useCallback(async () => {
    const current = generation.current;
    if (!current) return;
    current.cancelled = true;
    if (current.requestId) {
      try {
        await apiFetch("/api/requests/" + encodeURIComponent(current.requestId) + "/cancel", {
          method: "POST",
        });
      } catch {
        // Closing the SSE response still asks the server runtime to cancel in cleanup.
      }
    }
    current.controller.abort();
  }, []);

  return (
    <div className="relative rounded-2xl border bg-surface/80 backdrop-blur transition-all border-border-strong shadow-[var(--shadow-elegant)]">
      {activePending && (
        <div
          className="m-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm"
          role="alertdialog"
          aria-label="Xác nhận thao tác thay đổi"
        >
          <p className="font-medium">
            Orion muốn thực hiện: {activePending.summary.label || "Thao tác thay đổi"}
          </p>
          <p>Tool: {activePending.toolName}</p>
          <p>Target: {activePending.targetRef}</p>
          {Object.entries(activePending.summary)
            .filter(([key]) => key !== "label")
            .map(([key, detail]) => (
              <p key={key}>
                {key}: {detail}
              </p>
            ))}
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={resolvingAuthorization}
              onClick={() => void resolveAuthorization("deny")}
            >
              Từ chối
            </Button>
            <Button
              type="button"
              disabled={resolvingAuthorization}
              onClick={() => void resolveAuthorization("allow")}
            >
              Cho phép
            </Button>
          </div>
        </div>
      )}
      <Dialog open={autoWarning} onOpenChange={setAutoWarning}>
        <DialogContent className="max-w-md rounded-xl">
          <DialogHeader>
            <DialogTitle>Bật tự động sửa?</DialogTitle>
            <DialogDescription>
              Orion có thể thực hiện thao tác thay đổi mà không hỏi lại trong cuộc hội thoại này.
              Chỉ các tool và target được cấu hình mới được phép.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAutoWarning(false)}>
              Hủy
            </Button>
            <Button
              type="button"
              disabled={changingMode}
              onClick={() => {
                setAutoWarning(false);
                void (async () => {
                  setChangingMode(true);
                  try {
                    const sessionId = session?.id ?? (await createSession(projectId));
                    await setMutationMode(sessionId, "auto");
                  } catch (failure) {
                    setError(
                      failure instanceof Error ? failure.message : "Không thể đổi quyền sửa.",
                    );
                  } finally {
                    setChangingMode(false);
                  }
                })();
              }}
            >
              Bật tự động sửa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void submit();
          }
        }}
        placeholder="Nhắn tin cho Orion"
        rows={2}
        aria-label="Chat input"
        className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed placeholder:text-muted-foreground outline-none max-h-64"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <ModelStatus models={models} loading={loadingModels} />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Quyền sửa cuộc hội thoại"
              disabled={changingMode || Boolean(generation.current)}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface-2 px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {mutationMode === "read_only" ? (
                <LockKeyhole className="h-3.5 w-3.5" />
              ) : mutationMode === "confirm" ? (
                <Hand className="h-3.5 w-3.5" />
              ) : (
                <Zap className="h-3.5 w-3.5 text-amber-500" />
              )}
              <span>
                {mutationMode === "read_only"
                  ? "Chỉ đọc"
                  : mutationMode === "confirm"
                    ? "Hỏi trước khi sửa"
                    : "Tự động sửa"}
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            side="top"
            sideOffset={8}
            className="w-[min(17rem,calc(100vw-2rem))] rounded-xl p-1.5 shadow-lg"
          >
            {(
              [
                {
                  mode: "read_only",
                  label: "Chỉ đọc",
                  description: "Chỉ cho phép các thao tác đọc.",
                  Icon: LockKeyhole,
                },
                {
                  mode: "confirm",
                  label: "Hỏi trước khi sửa",
                  description: "Xác nhận từng thao tác thay đổi.",
                  Icon: Hand,
                },
                {
                  mode: "auto",
                  label: "Tự động sửa",
                  description: "Cho phép thay đổi mà không hỏi lại.",
                  Icon: Zap,
                },
              ] as const
            ).map(({ mode, label, description, Icon }) => (
              <DropdownMenuItem
                key={mode}
                onSelect={() => void changeMode(mode)}
                className="min-h-14 items-start gap-2.5 rounded-lg p-2.5"
              >
                <Icon className="mt-0.5 h-4 w-4" />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{label}</span>
                  <span className="block text-xs text-muted-foreground">{description}</span>
                </span>
                {mutationMode === mode && (
                  <Check aria-label="Đang chọn" className="mt-0.5 h-4 w-4" />
                )}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <div className="ml-auto flex items-center gap-2">
          {generation.current ? (
            <Button
              size="icon"
              variant="destructive"
              className="h-8 w-8 rounded-lg"
              onClick={() => void stop()}
              aria-label="Stop generating"
            >
              <Square className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              size="icon"
              className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
              onClick={() => void submit()}
              disabled={!value.trim() || (!loadingModels && models.length === 0)}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {error && (
        <div className="absolute bottom-14 left-4 right-4 text-xs text-destructive flex items-center gap-2">
          <AlertCircle className="h-3 w-3" />
          <span>Yêu cầu model thất bại: {error}</span>
        </div>
      )}
      <input
        ref={fileInput}
        type="file"
        accept=".txt,.md,.pdf,.docx,.xlsx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="sr-only"
        aria-label="Attach document"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void attachFile(file);
        }}
      />
      <div className="absolute bottom-2 left-2">
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          onClick={() => fileInput.current?.click()}
          disabled={uploading || Boolean(generation.current)}
          aria-label="Attach document"
          title="Đính kèm tài liệu"
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Paperclip className="h-4 w-4" />
          )}
        </Button>
      </div>
      {((projectId ? activeProjectDocuments : session?.documents || []).length ||
        attachmentError) && (
        <div className="border-t border-border px-3 py-2">
          <div className="flex flex-wrap gap-2">
            {(projectId ? activeProjectDocuments : session?.documents || []).map((document) => (
              <DocumentChip
                key={document.document.document_id}
                document={document}
                onDelete={() => {
                  if (projectId) {
                    void deleteProjectDocument(projectId, document.document.document_id)
                      .then(() => {
                        setProjectDocuments?.((current) =>
                          current.filter(
                            (item) => item.document.document_id !== document.document.document_id,
                          ),
                        );
                      })
                      .catch((reason: unknown) => {
                        setAttachmentError(
                          reason instanceof Error ? reason.message : "Unable to delete document.",
                        );
                      });
                  } else if (session) {
                    void deleteDocument(session.id, document.document.document_id);
                  }
                }}
              />
            ))}
          </div>
          {attachmentError && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
              <XCircle className="h-3.5 w-3.5" /> {attachmentError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DocumentChip({
  document,
  onDelete,
}: {
  document: Session["documents"][number];
  onDelete: () => void;
}) {
  const labels = {
    uploaded: "Đã tải lên",
    parsing: "Đang đọc",
    indexing: "Đang lập chỉ mục",
    ready: "Sẵn sàng",
    failed: "Không thể nhập",
  } as const;
  const pending =
    document.status === "uploaded" ||
    document.status === "parsing" ||
    document.status === "indexing";
  return (
    <div
      className="flex max-w-full items-center gap-2 rounded-lg border border-border bg-surface-2/70 px-2 py-1.5 text-xs"
      title={document.errorMessage || document.document.media_type || undefined}
    >
      {pending ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
      ) : (
        <FileText className="h-3.5 w-3.5 text-titanium" />
      )}
      <span className="max-w-40 truncate font-medium">{document.document.name}</span>
      {document.document.media_type && (
        <span className="max-w-28 truncate text-muted-foreground">
          {document.document.media_type}
        </span>
      )}
      <span
        className={
          document.status === "ready"
            ? "text-success"
            : document.status === "failed"
              ? "text-destructive"
              : "text-amber-400"
        }
      >
        {labels[document.status]}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-5 w-5 text-muted-foreground hover:text-destructive"
        onClick={onDelete}
        aria-label={`Delete ${document.document.name}`}
        title="Xóa tài liệu"
      >
        <Trash2 className="h-3 w-3" />
      </Button>
      {document.errorMessage && (
        <span className="max-w-56 truncate text-destructive">{document.errorMessage}</span>
      )}
    </div>
  );
}
