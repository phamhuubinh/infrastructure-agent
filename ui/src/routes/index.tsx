import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect, useCallback } from "react";
import {
  Share2,
  Sparkles,
  Send,
  AlertCircle,
  Square,
  ChevronDown,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ContextPanel } from "@/components/ContextPanel";
import { cn } from "@/lib/utils";
import { useChat, type Step, type Message } from "@/lib/chat-store";
import { UserMessage, AssistantMessage } from "@/components/chat/Message";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

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

const API_URL = import.meta.env.VITE_API_URL || "";

type ModelInfo = {
  name: string;
  model: string;
  provider: string;
  base_url: string;
  available: boolean;
};

function ChatPage() {
  const chatCtx = useChat();
  const [drag, setDrag] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedServer, setSelectedServer] = useState<string>("");
  const [loadingModels, setLoadingModels] = useState(true);
  const session = chatCtx.sessions.find(
    (s) => s.id === chatCtx.currentSessionId,
  );

  // Load available models on mount
  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      try {
        const res = await fetch(`${API_URL}/api/models`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        setModels(data.models || []);
        if (data.active_server) {
          setSelectedServer(data.active_server);
        } else if (data.models?.length > 0) {
          // Pre-select first available model
          const firstAvailable = data.models.find(
            (m: ModelInfo) => m.available,
          );
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
      <div
        className="flex-1 min-w-0 flex flex-col relative"
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
        }}
      >
        <div className="h-12 border-b border-border flex items-center gap-3 px-4 shrink-0">
          <div className="min-w-0 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium truncate">
              {session?.title || "Orion"}
            </span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label="Share"
            >
              <Share2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl w-full px-4 sm:px-6 py-8">
            {session && session.messages.length <= 1 ? (
              <EmptyState />
            ) : session ? (
              <Conversation messages={session.messages} />
            ) : null}
          </div>
        </div>

        <div className="border-t border-border bg-gradient-to-b from-background/50 to-background px-4 sm:px-6 py-4">
          <div className="mx-auto max-w-3xl w-full">
            <ChatInput
              models={models}
              selectedServer={selectedServer}
              setSelectedServer={setSelectedServer}
              loadingModels={loadingModels}
            />
            <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>
                Orion — kết quả có thể sai, hãy xác minh thông tin quan trọng.
              </span>
            </div>
          </div>
        </div>

        {drag && (
          <div className="absolute inset-0 pointer-events-none bg-primary/5 border-2 border-dashed border-primary/50 grid place-items-center">
            <div className="text-center">
              <div className="text-display text-3xl text-primary">
                Drop to attach
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                PDF, images, code
              </div>
            </div>
          </div>
        )}
      </div>

      {session && <ContextPanel session={session} />}
    </>
  );
}

function EmptyState() {
  const { createSession } = useChat();
  const suggestions = [
    { label: "Health", prompt: "Đánh giá sức khỏe của localhost" },
    { label: "Zabbix", prompt: "Zabbix đang có vấn đề gì?" },
    { label: "Services", prompt: "Có service nào bị lỗi?" },
    { label: "Security", prompt: "Security baseline có tốt không?" },
  ];
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center gap-6">
      <div className="relative">
        <div className="absolute inset-0 blur-2xl bg-primary/20 rounded-full" />
        <div className="relative h-14 w-14 rounded-2xl bg-gradient-to-br from-primary to-orange-500 grid place-items-center shadow-[var(--shadow-glow)]">
          <Sparkles className="h-6 w-6 text-primary-foreground" />
        </div>
      </div>
      <div>
        <h1 className="text-display text-4xl">Orion</h1>
        <p className="text-muted-foreground mt-1.5">Hỏi về hạ tầng của bạn.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl w-full">
        {suggestions.map((s) => (
          <button
            key={s.label}
            onClick={() => {
              const id = createSession();
              setTimeout(() => {
                document.dispatchEvent(
                  new CustomEvent("infra-send-prompt", {
                    detail: s.prompt,
                  }),
                );
              }, 50);
            }}
            className="w-full text-left text-sm text-foreground/85 hover:text-foreground rounded-md px-3 py-2.5 hover:bg-surface-2 transition-colors border border-border"
          >
            {s.prompt}
          </button>
        ))}
      </div>
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
            className="h-1.5 w-1.5 rounded-full bg-primary/70 animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
    </div>
  );
}

function Conversation({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="space-y-8">
      {messages.map((msg, i) => (
        <div key={i}>
          {msg.role === "user" ? (
            <UserMessage content={msg.content}>{msg.content}</UserMessage>
          ) : msg.content ? (
            <AssistantMessage agent="Orion" content={msg.content}>
              <Card className="p-4 border-border/50">
                <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:bg-surface-2 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-mono [&_code]:text-[12.5px] [&_p]:leading-relaxed [&_p]:text-foreground/95">
                  <Markdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </Markdown>
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
        title={
          selectedModel ? `${selectedModel.model} (${selectedModel.provider})` : "Chọn model"
        }
      >
        {loadingModels ? (
          <Loader2 className="h-3 w-3 animate-spin" />
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
                  <span className="truncate">
                    {m.model}
                  </span>
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
}: {
  models: ModelInfo[];
  selectedServer: string;
  setSelectedServer: (name: string) => void;
  loadingModels: boolean;
}) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const selectedServerRef = useRef(selectedServer);
  selectedServerRef.current = selectedServer;
  const { getSession, updateSession, renameSession } = useChat();

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setValue(detail);
      setTimeout(() => handleSubmit(detail), 10);
    };
    document.addEventListener("infra-send-prompt", handler);
    return () => document.removeEventListener("infra-send-prompt", handler);
  }, []);

  const resetIdleTimer = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = null;
  }, []);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    resetIdleTimer();
    const updated = getSession();
    if (updated && streamingContent) {
      const lastMsg = updated.messages[updated.messages.length - 1];
      if (lastMsg?.role === "assistant") {
        updateSession({ messages: updated.messages.slice(0, -1) });
      }
      const assistantMsg: Message = {
        role: "assistant",
        content: streamingContent || "(interrupted)",
      };
      updateSession({
        messages: [
          ...(getSession()?.messages || updated.messages),
          assistantMsg,
        ],
      });
    }
    setStreamingContent("");
    setLoading(false);
    setPipelineStatus(null);
  }, [streamingContent]);

  const startIdleTimer = useCallback(() => {
    resetIdleTimer();
    idleTimerRef.current = window.setTimeout(async () => {
      try {
        const healthController = new AbortController();
        const healthTimer = setTimeout(() => healthController.abort(), 5000);
        const healthRes = await fetch(`${API_URL}/api/check-model`, {
          signal: healthController.signal,
        });
        clearTimeout(healthTimer);
        if (healthRes.ok) {
          setPipelineStatus("Model đang xử lý, vui lòng đợi...");
          startIdleTimer();
        } else {
          handleStop();
          setError("Model không phản hồi, vui lòng thử lại sau.");
        }
      } catch {
        handleStop();
        setError("Model không phản hồi, vui lòng thử lại sau.");
      }
    }, 60000);
  }, [handleStop, resetIdleTimer]);

  async function handleSubmit(text?: string) {
    const question = (text ?? value).trim();
    if (!question || loading) return;

    const session = getSession();
    if (!session) return;

    if (session.title === "New chat") {
      const newTitle =
        question.length > 60 ? question.slice(0, 57) + "..." : question;
      updateSession({ title: newTitle });
      renameSession(session.id, newTitle);
    }

    setValue("");
    setError(null);
    setPipelineStatus("Đang phân tích intent...");
    setStreamingContent("");

    const userMsg: Message = { role: "user", content: question };
    const thinkingMsg: Message = { role: "assistant", content: "", steps: [] };
    updateSession({ messages: [...session.messages, userMsg, thinkingMsg] });
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const history = session.messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const connTimeout = setTimeout(() => controller.abort(), 180000);

      const rawId = getSession()?.id;
      const sessionId =
        rawId && !rawId.startsWith("pending_") ? rawId : undefined;
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          messages: history,
          session_id: sessionId,
          server_name: selectedServerRef.current || undefined,
        }),
        signal: controller.signal,
      });

      clearTimeout(connTimeout);

      if (!res.ok) throw new Error(await res.text());

      setPipelineStatus("Đang nhận phản hồi...");

      // Non-streaming fallback
      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("text/event-stream")) {
        const data = await res.json();
        setPipelineStatus(null);

        const updated = getSession();
        if (!updated) return;

        const msgs = [...updated.messages];
        msgs[msgs.length - 1] = {
          role: "assistant",
          content: data.assessment || "(empty response)",
          steps: data.steps,
        };
        updateSession({ messages: msgs });
        setLoading(false);
        return;
      }

      // Streaming
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let steps: Step[] | undefined;
      let buffer = "";

      const assistantPlaceholder: Message = {
        role: "assistant",
        content: "",
      };
      updateSession({
        messages: [
          ...(getSession()?.messages || []),
          assistantPlaceholder,
        ],
      });

      setPipelineStatus(null);
      startIdleTimer();

      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) break;

        resetIdleTimer();
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
                setStreamingContent(fullContent);
                const updated = getSession();
                if (updated) {
                  const msgs = [...updated.messages];
                  msgs[msgs.length - 1] = {
                    ...msgs[msgs.length - 1],
                    content: fullContent,
                  };
                  updateSession({ messages: msgs });
                }
              }
              if (parsed.steps) {
                steps = parsed.steps;
              }
            } catch {}
          }
        }
      }

      resetIdleTimer();
      const finalUpdated = getSession();
      if (finalUpdated) {
        const msgs = [...finalUpdated.messages];
        msgs[msgs.length - 1] = {
          role: "assistant",
          content: fullContent || "(empty response)",
          steps,
        };
        updateSession({ messages: msgs });
      }
      setStreamingContent("");
    } catch (err: any) {
      if (err.name === "AbortError") {
        if (streamingContent) {
          const updated = getSession();
          if (updated) {
            const msgs = [...updated.messages];
            msgs[msgs.length - 1] = {
              role: "assistant",
              content: streamingContent,
            };
            updateSession({ messages: msgs });
          }
        }
      } else {
        setError(err.message || "Request failed");
      }
    } finally {
      abortRef.current = null;
      resetIdleTimer();
      setLoading(false);
      setPipelineStatus(null);
      setStreamingContent("");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="relative rounded-2xl border bg-surface/80 backdrop-blur transition-all border-border-strong shadow-[var(--shadow-elegant)]">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Hỏi về hạ tầng…"
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
          <kbd className="hidden sm:inline text-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-muted-foreground border border-border">
            ⏎
          </kbd>
          {loading ? (
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
              className="h-8 w-8 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={() => handleSubmit()}
              disabled={!value.trim()}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {error && (
        <div className="absolute bottom-14 left-4 right-4">
          <div className="text-xs text-destructive flex items-center gap-2">
            <AlertCircle className="h-3 w-3" />
            {error}
          </div>
        </div>
      )}
    </div>
  );
}