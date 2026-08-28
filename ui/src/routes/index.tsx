import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  FileText,
  Loader2,
  Paperclip,
  Send,
  Square,
  Trash2,
  XCircle,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ContextPanel } from "@/components/ContextPanel";
import { OrionIcon } from "@/components/OrionIcon";
import { AssistantMessage, UserMessage } from "@/components/chat/Message";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  apiErrorMessage,
  apiFetch,
  attachProjectDocument,
  deleteProjectDocument,
  projectDocuments,
  type Project,
} from "@/lib/api";
import {
  useChat,
  sessionFromTimeline,
  type Message,
  type RuntimeEvent,
  type Session,
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
  cancelled: boolean;
};

export function parseSseEvents(buffer: string): { events: RuntimeEvent[]; remainder: string } {
  const frames = buffer.split("\n\n");
  const remainder = frames.pop() || "";
  const events = frames.flatMap((frame): RuntimeEvent[] => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (!data) return [];
    try {
      const parsed = JSON.parse(data) as RuntimeEvent;
      return typeof parsed.type === "string" && parsed.payload ? [parsed] : [];
    } catch {
      return [];
    }
  });
  return { events, remainder };
}

export function ChatPage({ project }: { project?: Project }) {
  const chat = useChat();
  const navigate = useNavigate();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [selectedSourceRefId, setSelectedSourceRefId] = useState<string | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const loadedInitialScope = useRef<string | null>(null);
  const session = chat.sessions.find(
    (item) =>
      item.id === chat.currentSessionId &&
      (project ? item.projectId === project.project_id : !item.projectId),
  );
  const [projectDocs, setProjectDocs] = useState<Session["documents"]>([]);
  const displayedSession =
    project && session
      ? {
          ...session,
          sources: sessionFromTimeline(
            session.id,
            session.timeline,
            [...session.documents, ...projectDocs],
            session.projectId,
          ).sources,
        }
      : session;

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
    const candidate = chat.sessions.find((item) =>
      project ? item.projectId === project.project_id : item.projectId === null,
    );
    if (!candidate) {
      if (project) void chat.createSession(project.project_id);
      return;
    }
    void chat.switchSession(candidate.id);
  }, [chat, project]);

  useEffect(() => {
    if (!project) return;
    let disposed = false;
    void projectDocuments(project.project_id)
      .then((documents) => {
        if (!disposed) {
          setProjectDocs(
            documents.map((document) => ({
              document: document.document,
              attachmentId: document.attachment_id,
              status: document.status,
              errorMessage: document.error_message,
              ingestion: document.ingestion || [],
            })),
          );
        }
      })
      .catch(() => {
        if (!disposed) setProjectDocs([]);
      });
    return () => {
      disposed = true;
    };
  }, [project]);

  const handleConversationScroll = useCallback(() => {
    const element = scrollAreaRef.current;
    if (!element) return;
    setShowScrollToBottom(element.scrollHeight - element.scrollTop - element.clientHeight > 140);
  }, []);

  return (
    <>
      <div className="flex-1 min-w-0 flex flex-col relative">
        <div
          ref={scrollAreaRef}
          onScroll={handleConversationScroll}
          className="flex-1 overflow-y-auto"
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
              onClick={() =>
                scrollAreaRef.current?.scrollTo({
                  top: scrollAreaRef.current.scrollHeight,
                  behavior: "smooth",
                })
              }
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
              setProjectDocuments={setProjectDocs}
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
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div className="space-y-8">
      {messages.map((message) => (
        <div key={message.itemId}>
          {message.role === "user" ? (
            <UserMessage content={message.content} askedAt={message.askedAt}>
              {message.content}
            </UserMessage>
          ) : message.content.trim() ? (
            <AssistantMessage agent="Orion" content={message.content}>
              <Card className="p-4 border-border/50">
                <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:bg-surface-2 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-mono [&_code]:text-[12.5px] [&_p]:leading-relaxed [&_p]:text-foreground/95">
                  <Markdown remarkPlugins={[remarkGfm]}>
                    {displayAssistantContent(message.content)}
                  </Markdown>
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
      <div ref={bottomRef} />
    </div>
  );
}

function displayAssistantContent(content: string) {
  // Citation IDs are runtime provenance, not user-facing document text. Source cards below are
  // rendered only after the IDs resolve against canonical, currently available SourceRefs.
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
  const cited = sourceRefIds.flatMap((sourceRefId) => {
    const source = byId.get(sourceRefId);
    return source ? [source] : [];
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
  setProjectDocuments: (documents: Session["documents"]) => void;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const generation = useRef<Generation | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const {
    currentSessionId,
    sessions,
    createSession,
    addOptimisticMessage,
    addOptimisticAssistant,
    appendAssistantDelta,
    reconcileAssistantMessage,
    loadSession,
    recordEvent,
    setSessionGenerating,
    attachDocument,
    deleteDocument,
  } = useChat();
  const session = sessions.find(
    (item) =>
      item.id === currentSessionId && (projectId ? item.projectId === projectId : !item.projectId),
  );

  const attachFile = useCallback(
    async (file: File) => {
      setAttachmentError(null);
      setUploading(true);
      try {
        if (projectId) {
          const uploaded = await attachProjectDocument(projectId, {
            name: file.name,
            content: await file.text(),
            media_type: file.type || "text/plain",
          });
          setProjectDocuments([
            ...activeProjectDocuments,
            {
              document: uploaded.document,
              attachmentId: uploaded.attachment_id,
              status: uploaded.status,
              errorMessage: uploaded.error_message,
              ingestion: [],
            },
          ]);
        } else {
          let sessionId = currentSessionId;
          if (!sessionId) sessionId = await createSession();
          await attachDocument(sessionId, {
            name: file.name,
            content: await file.text(),
            mediaType: file.type || "text/plain",
          });
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
    [
      activeProjectDocuments,
      attachDocument,
      createSession,
      currentSessionId,
      projectId,
      setProjectDocuments,
    ],
  );

  const submit = useCallback(async () => {
    const content = value.trim();
    if (!content || generation.current) return;
    setError(null);
    let sessionId = session?.id || null;
    try {
      if (!sessionId) sessionId = await createSession(projectId);
      addOptimisticMessage(sessionId, content);
      addOptimisticAssistant(sessionId);
      setValue("");
      setSessionGenerating(sessionId, true);
      const controller = new AbortController();
      const current: Generation = { controller, requestId: null, cancelled: false };
      generation.current = current;
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
          if (event.type === "assistant.delta" && typeof event.payload.content === "string") {
            appendAssistantDelta(sessionId, event.payload.content);
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
      if (sessionId) setSessionGenerating(sessionId, false);
      generation.current = null;
    }
  }, [
    addOptimisticAssistant,
    addOptimisticMessage,
    appendAssistantDelta,
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
                    void deleteProjectDocument(projectId, document.document.document_id).then(() =>
                      setProjectDocuments(
                        activeProjectDocuments.filter(
                          (item) => item.document.document_id !== document.document.document_id,
                        ),
                      ),
                    );
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
