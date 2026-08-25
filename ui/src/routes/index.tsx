import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowDown, Loader2, Send, Square } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ContextPanel } from "@/components/ContextPanel";
import { OrionIcon } from "@/components/OrionIcon";
import { AssistantMessage, UserMessage } from "@/components/chat/Message";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { apiErrorMessage, apiFetch } from "@/lib/api";
import { useChat, type Message, type RuntimeEvent, type TimelineItem } from "@/lib/chat-store";

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

export function ChatPage() {
  const chat = useChat();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const session = chat.sessions.find((item) => item.id === chat.currentSessionId);

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
            {!session || session.messages.length === 0 ? (
              <EmptyState />
            ) : (
              <Conversation
                messages={session.messages}
                generating={chat.generatingSessions.has(session.id)}
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
            <ChatInput models={models} loadingModels={loadingModels} />
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

function Conversation({ messages, generating }: { messages: Message[]; generating: boolean }) {
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
          ) : message.content ? (
            <AssistantMessage agent="Orion" content={message.content}>
              <Card className="p-4 border-border/50">
                <div className="prose prose-sm max-w-none dark:prose-invert [&_pre]:bg-surface-2 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-lg [&_pre]:p-3 [&_code]:text-mono [&_code]:text-[12.5px] [&_p]:leading-relaxed [&_p]:text-foreground/95">
                  <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
                </div>
              </Card>
            </AssistantMessage>
          ) : (
            <ThinkingDots />
          )}
        </div>
      ))}
      {generating && messages.at(-1)?.content !== "" && <ThinkingDots />}
      <div ref={bottomRef} />
    </div>
  );
}

function ModelStatus({ models, loading }: { models: ModelInfo[]; loading: boolean }) {
  const model = models[0];
  return (
    <div
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
      <span className="max-w-[140px] truncate">{model?.model_id || "No model"}</span>
    </div>
  );
}

function ChatInput({ models, loadingModels }: { models: ModelInfo[]; loadingModels: boolean }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const generation = useRef<Generation | null>(null);
  const {
    currentSessionId,
    createSession,
    addOptimisticMessage,
    addOptimisticAssistant,
    appendAssistantDelta,
    reconcileAssistantMessage,
    loadSession,
    recordEvent,
    setSessionGenerating,
  } = useChat();

  const submit = useCallback(async () => {
    const content = value.trim();
    if (!content || generation.current) return;
    setError(null);
    let sessionId = currentSessionId;
    try {
      if (!sessionId) sessionId = await createSession();
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
          if (event.type === "request.started" && typeof event.payload.request_id === "string") {
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
    currentSessionId,
    loadSession,
    recordEvent,
    reconcileAssistantMessage,
    setSessionGenerating,
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
              disabled={!value.trim()}
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
          {error}
        </div>
      )}
    </div>
  );
}
