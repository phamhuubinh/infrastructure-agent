import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Send, AlertCircle, Square, ChevronDown, Loader2, ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ContextPanel } from "@/components/ContextPanel";
import { OrionIcon } from "@/components/OrionIcon";
import { cn } from "@/lib/utils";
import { useChat, type Step, type Message } from "@/lib/chat-store";
import { UserMessage, AssistantMessage } from "@/components/chat/Message";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiErrorMessage, apiFetch } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Orion" },
      {
        name: "description",
        content: "Orion — Infrastructure Investigation Platform",
      },
    ],
  }),
  component: ChatPage,
});

type ModelInfo = {
  name: string;
  model: string;
  provider: string;
  base_url: string;
  available: boolean;
};

/** Per-session generation state tracked independently for each session. */
type SessionGenState = {
  loading: boolean;
  streamingContent: string;
  pipelineStatus: string | null;
  error: string | null;
  abortRef: AbortController | null;
  idleTimerRef: number | null;
  startedAt: number | null;
  generation: number;
};

function ChatPage() {
  const chatCtx = useChat();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [loadingModels, setLoadingModels] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const regenerateRef = useRef<((assistantMessageIndex: number) => void) | null>(null);
  const session = chatCtx.sessions.find((s) => s.id === chatCtx.currentSessionId);

  const regenerateMessage = useCallback((assistantMessageIndex: number) => {
    regenerateRef.current?.(assistantMessageIndex);
  }, []);

  const handleConversationScroll = useCallback(() => {
    const element = scrollAreaRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 140);
  }, []);

  const scrollToBottom = useCallback(() => {
    const element = scrollAreaRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
  }, []);

  // Load available models on mount
  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      try {
        const res = await apiFetch("/api/models");
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        setModels(data.models || []);
        if (data.active_server) {
          setSelectedServer(data.active_server);
        } else if (data.models?.length > 0) {
          const firstAvailable = data.models.find((m: ModelInfo) => m.available);
          if (firstAvailable) {
            setSelectedServer(firstAvailable.name);
          }
        }
      } catch {
        // Server not available
      }
      setLoadingModels(false);
    }
    loadModels();
    return () => {
      cancelled = true;
    };
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
            {!session || session.messages.length <= 1 ? (
              <EmptyState />
            ) : (
              <Conversation
                messages={session.messages}
                onRegenerate={regenerateMessage}
                regenerating={chatCtx.generatingSessions.has(session.id)}
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
              onClick={scrollToBottom}
              className="absolute -top-12 left-1/2 z-20 h-9 w-9 -translate-x-1/2 rounded-full bg-background shadow-lg"
              aria-label="Đi đến cuối cuộc trò chuyện"
              title="Đi đến cuối cuộc trò chuyện"
            >
              <ArrowDown className="h-4 w-4" />
            </Button>
          )}
          <div className="mx-auto w-full max-w-6xl">
            <ChatInput
              models={models}
              selectedServer={selectedServer}
              setSelectedServer={setSelectedServer}
              loadingModels={loadingModels}
              regenerateRef={regenerateRef}
            />
            <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Orion — kết quả có thể sai, hãy xác minh thông tin quan trọng.</span>
            </div>
          </div>
        </div>
      </div>

      {session && <ContextPanel session={session} />}
    </>
  );
}

function EmptyState() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center gap-6">
      <div className="relative">
        <OrionIcon className="relative h-14 w-14" />
      </div>
      <h1 className="text-display text-4xl">Orion</h1>
    </div>
  );
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-2">
      <span className="text-sm font-medium text-muted-foreground">Orion</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-titanium/70"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
    </div>
  );
}

function Conversation({
  messages,
  onRegenerate,
  regenerating,
}: {
  messages: Message[];
  onRegenerate: (assistantMessageIndex: number) => void;
  regenerating: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const lastAssistantIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].content) {
        return i;
      }
    }
    return -1;
  }, [messages]);

  return (
    <div className="space-y-8">
      {messages.map((msg, i) => (
        <div key={i}>
          {msg.role === "user" ? (
            <UserMessage content={msg.content} askedAt={msg.askedAt}>
              {msg.content}
            </UserMessage>
          ) : msg.content ? (
            <AssistantMessage
              agent="Orion"
              content={msg.content}
              responseTimeMs={msg.responseTimeMs}
              onRegenerate={i === lastAssistantIndex ? () => onRegenerate(i) : undefined}
              regenerateDisabled={regenerating}
            >
              <Card className="p-4 border-border/50">
                <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:bg-surface-2 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-mono [&_code]:text-[12.5px] [&_p]:leading-relaxed [&_p]:text-foreground/95">
                  <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                </div>
              </Card>
            </AssistantMessage>
          ) : (
            <ThinkingDots />
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function ModelSelector({
  models,
  selectedServer,
  setSelectedServer,
  loadingModels,
}: {
  models: ModelInfo[];
  selectedServer: string;
  setSelectedServer: (name: string) => void;
  loadingModels: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedModel = models.find((m) => m.name === selectedServer);
  const availableModels = models.filter((m) => m.available);
  const unavailableModels = models.filter((m) => !m.available);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md border transition-colors",
          selectedModel?.available
            ? "border-border hover:bg-surface-2 text-foreground"
            : "border-destructive/30 text-muted-foreground",
        )}
        disabled={loadingModels}
        title={selectedModel ? `${selectedModel.model} (${selectedModel.provider})` : "Chọn model"}
      >
        {loadingModels ? (
          <Loader2 className="h-3 w-3 animate-spin text-titanium" />
        ) : selectedModel ? (
          <>
            <span
              className={cn(
                "inline-block h-1.5 w-1.5 rounded-full",
                selectedModel.available ? "bg-success" : "bg-destructive",
              )}
            />
            <span className="max-w-[100px] truncate">{selectedModel.model}</span>
          </>
        ) : (
          <span className="text-muted-foreground">No model</span>
        )}
        <ChevronDown className="h-3 w-3 opacity-50" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-64 rounded-md border bg-popover text-popover-foreground shadow-md z-50 py-1">
          {availableModels.length > 0 && (
            <>
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                Có sẵn
              </div>
              {availableModels.map((m) => (
                <button
                  key={m.name}
                  type="button"
                  onClick={() => {
                    setSelectedServer(m.name);
                    setOpen(false);
                  }}
                  className={cn(
                    "w-full text-left px-3 py-1.5 text-[12px] flex items-center gap-2 hover:bg-accent transition-colors",
                    m.name === selectedServer && "bg-accent",
                  )}
                >
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-success shrink-0" />
                  <span className="truncate">{m.model}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
                    {m.provider}
                  </span>
                </button>
              ))}
            </>
          )}

          {unavailableModels.length > 0 && (
            <>
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground mt-1 border-t border-border">
                Không khả dụng
              </div>
              {unavailableModels.map((m) => (
                <div
                  key={m.name}
                  className="w-full text-left px-3 py-1.5 text-[12px] flex items-center gap-2 opacity-40 cursor-not-allowed"
                >
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-destructive shrink-0" />
                  <span className="truncate">{m.model}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
                    {m.provider}
                  </span>
                </div>
              ))}
            </>
          )}

          {models.length === 0 && !loadingModels && (
            <div className="px-3 py-2 text-[11px] text-muted-foreground">
              Không có model nào được cấu hình
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ChatInput({
  models,
  selectedServer,
  setSelectedServer,
  loadingModels,
  regenerateRef,
}: {
  models: ModelInfo[];
  selectedServer: string;
  setSelectedServer: (name: string) => void;
  loadingModels: boolean;
  regenerateRef: React.MutableRefObject<((assistantMessageIndex: number) => void) | null>;
}) {
  const [value, setValue] = useState("");
  const selectedServerRef = useRef(selectedServer);
  selectedServerRef.current = selectedServer;

  const {
    currentSessionId,
    createSession,
    getSession,
    updateSession,
    updateSessionById,
    renameSession,
    setSessionGenerating,
  } = useChat();

  // Per-session generation state, keyed by session ID.
  // This allows multiple sessions to generate concurrently.
  const sessionGenRef = useRef<Map<string, SessionGenState>>(new Map());
  const handleSubmitRef = useRef<(override?: string) => void>(() => undefined);

  function getGen(sid: string | null): SessionGenState {
    if (!sid) {
      return {
        loading: false,
        streamingContent: "",
        pipelineStatus: null,
        error: null,
        abortRef: null,
        idleTimerRef: null,
        startedAt: null,
        generation: 0,
      };
    }
    let st = sessionGenRef.current.get(sid);
    if (!st) {
      st = {
        loading: false,
        streamingContent: "",
        pipelineStatus: null,
        error: null,
        abortRef: null,
        idleTimerRef: null,
        startedAt: null,
        generation: 0,
      };
      sessionGenRef.current.set(sid, st);
    }
    return st;
  }

  // Compute the current session's gen state for rendering
  const gen = useMemo(() => getGen(currentSessionId), [currentSessionId]);

  useEffect(() => {
    setValue("");
  }, [currentSessionId]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setValue(detail);
      setTimeout(() => handleSubmitRef.current(detail), 10);
    };
    document.addEventListener("infra-send-prompt", handler);
    return () => document.removeEventListener("infra-send-prompt", handler);
  }, []);

  const resetIdleTimer = useCallback((g: SessionGenState) => {
    if (g.idleTimerRef) clearTimeout(g.idleTimerRef);
    g.idleTimerRef = null;
  }, []);

  function elapsedResponseTime(g: SessionGenState) {
    return g.startedAt === null ? undefined : Math.round(performance.now() - g.startedAt);
  }

  const handleStop = useCallback(() => {
    const sid = currentSessionId;
    const g = getGen(sid);
    g.abortRef?.abort();
    g.abortRef = null;
    resetIdleTimer(g);

    const updated = getSession();
    if (updated && g.streamingContent) {
      const lastMsg = updated.messages[updated.messages.length - 1];
      if (lastMsg?.role === "assistant") {
        updateSession({ messages: updated.messages.slice(0, -1) });
      }
      const assistantMsg: Message = {
        role: "assistant",
        content: g.streamingContent || "(interrupted)",
        responseTimeMs: elapsedResponseTime(g),
      };
      updateSession({
        messages: [...(getSession()?.messages || updated.messages), assistantMsg],
      });
    }
    g.streamingContent = "";
    g.loading = false;
    g.pipelineStatus = null;
    g.startedAt = null;
    setSessionGenerating(sid!, false);
  }, [currentSessionId, getSession, updateSession, resetIdleTimer, setSessionGenerating]);

  const startIdleTimer = useCallback(
    (sid: string, generation: number, g: SessionGenState) => {
      resetIdleTimer(g);
      g.idleTimerRef = window.setTimeout(async () => {
        if (sessionGenRef.current.get(sid) !== g || g.generation !== generation) return;
        try {
          const healthController = new AbortController();
          const healthTimer = setTimeout(() => healthController.abort(), 5000);
          const healthRes = await apiFetch("/api/check-model", {
            signal: healthController.signal,
          });
          clearTimeout(healthTimer);
          const health = healthRes.ok ? await healthRes.json() : null;
          if (health?.health_state === "healthy") {
            g.pipelineStatus = "Model đang xử lý, vui lòng đợi...";
            startIdleTimer(sid, generation, g);
          } else {
            g.abortRef?.abort();
            g.error = "Model không phản hồi, vui lòng thử lại sau.";
          }
        } catch {
          g.abortRef?.abort();
          g.error = "Model không phản hồi, vui lòng thử lại sau.";
        }
      }, 60000);
    },
    [resetIdleTimer],
  );

  /** Update messages for a specific session by its ID (for background sessions). */
  const setSidMessages = useCallback(
    (
      sid: string,
      baseMessages: Message[],
      content: string,
      steps: Step[] | undefined,
      responseTimeMs?: number,
    ) => {
      const msgs = [...baseMessages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content, steps, responseTimeMs };
      } else {
        msgs.push({ role: "assistant", content, steps, responseTimeMs });
      }
      updateSessionById(sid, { messages: msgs });
    },
    [updateSessionById],
  );

  async function handleSubmit(text?: string, regenerateAssistantIndex?: number) {
    const startedAt = performance.now();
    let sid = currentSessionId;
    let session = getSession();
    const isRegeneration = regenerateAssistantIndex !== undefined;
    let question = (text ?? value).trim();
    let askedAt = new Date().toISOString();
    let regenerateTurnIndex: number | undefined;
    let originalMessages: Message[] | null = null;
    let retainedMessages: Message[] | null = null;

    if (isRegeneration) {
      if (!sid || !session) return;
      const assistantMessage = session.messages[regenerateAssistantIndex];
      if (assistantMessage?.role !== "assistant") return;

      let userMessageIndex = regenerateAssistantIndex - 1;
      while (userMessageIndex >= 0 && session.messages[userMessageIndex].role !== "user") {
        userMessageIndex -= 1;
      }
      if (userMessageIndex < 0) return;

      const userMessage = session.messages[userMessageIndex];
      question = userMessage.content.trim();
      if (!question) return;
      askedAt = userMessage.askedAt || askedAt;
      regenerateTurnIndex =
        session.messages.slice(0, userMessageIndex + 1).filter((message) => message.role === "user")
          .length - 1;
      originalMessages = session.messages;
      retainedMessages = session.messages.slice(0, userMessageIndex + 1);
    } else if (!question) {
      return;
    }

    if (!sid || !session) {
      sid = await createSession();
      session = getSession();
    }
    if (!session) return;

    const g = getGen(sid);
    if (g.loading) return;

    if (!isRegeneration && session.title === "New chat") {
      const newTitle = question.length > 60 ? question.slice(0, 57) + "..." : question;
      updateSession({ title: newTitle });
      renameSession(session.id, newTitle);
    }

    if (!isRegeneration) setValue("");
    g.error = null;
    g.pipelineStatus = "Đang phân tích intent...";
    g.streamingContent = "";
    g.startedAt = startedAt;
    g.generation += 1;
    const generation = g.generation;

    const thinkingMsg: Message = {
      role: "assistant",
      content: "",
      steps: [],
    };
    const historyMessages = isRegeneration ? retainedMessages!.slice(0, -1) : session.messages;
    const requestMessages = isRegeneration
      ? [...retainedMessages!, thinkingMsg]
      : [
          ...session.messages,
          { role: "user", content: question, askedAt } satisfies Message,
          thinkingMsg,
        ];
    updateSession({ messages: requestMessages });
    g.loading = true;
    setSessionGenerating(sid, true);

    const controller = new AbortController();
    g.abortRef = controller;

    try {
      const history = historyMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const connTimeout = setTimeout(() => controller.abort(), 180000);

      const rawId = sid;
      const sessionId = rawId || undefined;
      const res = await apiFetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          messages: history,
          session_id: sessionId,
          server_name: selectedServerRef.current || undefined,
          asked_at: askedAt,
          ...(regenerateTurnIndex !== undefined
            ? { regenerate_turn_index: regenerateTurnIndex }
            : {}),
        }),
        signal: controller.signal,
      });

      clearTimeout(connTimeout);

      if (!res.ok) throw new Error(await apiErrorMessage(res));

      g.pipelineStatus = "Đang nhận phản hồi...";

      // Non-streaming fallback
      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("text/event-stream")) {
        const data = await res.json();
        g.pipelineStatus = null;

        const msgs = [...requestMessages];
        msgs[msgs.length - 1] = {
          role: "assistant",
          content: data.assessment || "(empty response)",
          steps: data.steps,
          responseTimeMs: data.response_time_ms ?? elapsedResponseTime(g),
        };
        updateSessionById(sid, { messages: msgs });
        g.loading = false;
        setSessionGenerating(sid, false);
        return;
      }

      // Streaming
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let steps: Step[] | undefined;
      let buffer = "";

      g.pipelineStatus = null;
      startIdleTimer(sid, generation, g);

      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) break;

        resetIdleTimer(g);
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") break;
            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                fullContent += parsed.content;
                g.streamingContent = fullContent;
                setSidMessages(sid, requestMessages, fullContent, steps);
              }
              if (parsed.steps) {
                steps = parsed.steps;
              }
            } catch {
              // skip malformed SSE chunks
            }
          }
        }
      }

      resetIdleTimer(g);
      setSidMessages(
        sid,
        requestMessages,
        fullContent || "(empty response)",
        steps,
        elapsedResponseTime(g),
      );
      g.streamingContent = "";
    } catch (err: unknown) {
      const error = err instanceof Error ? err : new Error(String(err));
      if (error.name === "AbortError") {
        if (g.streamingContent) {
          setSidMessages(
            sid,
            requestMessages,
            g.streamingContent,
            undefined,
            elapsedResponseTime(g),
          );
        } else if (originalMessages) {
          updateSessionById(sid, { messages: originalMessages });
        }
      } else {
        g.error = error.message || "Request failed";
        if (originalMessages) {
          updateSessionById(sid, { messages: originalMessages });
        }
      }
    } finally {
      g.abortRef = null;
      resetIdleTimer(g);
      g.loading = false;
      g.pipelineStatus = null;
      g.streamingContent = "";
      g.startedAt = null;
      setSessionGenerating(sid, false);
    }
  }

  handleSubmitRef.current = handleSubmit;
  regenerateRef.current = (assistantMessageIndex) => {
    void handleSubmit(undefined, assistantMessageIndex);
  };

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="relative rounded-2xl border bg-surface/80 backdrop-blur transition-all border-border-strong shadow-[var(--shadow-elegant)]">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Nhắn tin cho Orion"
        rows={2}
        className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed placeholder:text-muted-foreground outline-none max-h-64"
      />
      <div className="flex items-center gap-1 px-2 pb-2">
        <div className="flex items-center gap-1.5">
          <ModelSelector
            models={models}
            selectedServer={selectedServer}
            setSelectedServer={setSelectedServer}
            loadingModels={loadingModels}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {gen.loading ? (
            <Button
              size="icon"
              variant="destructive"
              className="h-8 w-8 rounded-lg"
              onClick={handleStop}
              aria-label="Stop generating"
            >
              <Square className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              size="icon"
              className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active"
              onClick={() => handleSubmit()}
              disabled={!value.trim()}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {gen.error && (
        <div className="absolute bottom-14 left-4 right-4">
          <div className="text-xs text-destructive flex items-center gap-2">
            <AlertCircle className="h-3 w-3" />
            {gen.error}
          </div>
        </div>
      )}
    </div>
  );
}
