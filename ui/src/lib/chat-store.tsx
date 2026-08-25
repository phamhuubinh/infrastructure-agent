import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiJson } from "@/lib/api";

const SESSION_IDS_STORAGE = "orion-m1-session-ids";

export type TimelineKind =
  "user_message" | "assistant_message" | "tool_call" | "tool_result" | "runtime_notice";

export type TimelineItem = {
  item_id: string;
  session_id: string;
  created_at: string;
  kind: TimelineKind;
  payload: Record<string, unknown>;
  call_id: string | null;
  tool_name: string | null;
};

export type RuntimeEvent = {
  type: string;
  created_at: string;
  payload: Record<string, unknown>;
};

export type ToolActivity = {
  callId: string;
  toolName: string;
  status: "started" | "completed" | "failed";
};

export type Message = {
  itemId: string;
  role: "user" | "assistant";
  content: string;
  askedAt?: string;
};

export type Session = {
  id: string;
  title: string;
  timeline: TimelineItem[];
  messages: Message[];
  activity: ToolActivity[];
};

type ChatContextValue = {
  sessions: Session[];
  currentSessionId: string | null;
  generatingSessions: Set<string>;
  createSession: () => Promise<string>;
  startNewChat: () => void;
  switchSession: (id: string) => Promise<void>;
  loadSession: (id: string) => Promise<void>;
  addOptimisticMessage: (sessionId: string, content: string) => void;
  addOptimisticAssistant: (sessionId: string) => void;
  appendAssistantDelta: (sessionId: string, content: string) => void;
  reconcileAssistantMessage: (sessionId: string, item: TimelineItem) => void;
  recordEvent: (sessionId: string, event: RuntimeEvent) => void;
  setSessionGenerating: (sessionId: string, generating: boolean) => void;
};

const ChatContext = createContext<ChatContextValue>(null!);

export function useChat() {
  return useContext(ChatContext);
}

function rememberedSessionIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = JSON.parse(window.localStorage.getItem(SESSION_IDS_STORAGE) || "[]");
    return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function rememberSession(id: string) {
  if (typeof window === "undefined") return;
  const next = [id, ...rememberedSessionIds().filter((known) => known !== id)].slice(0, 20);
  window.localStorage.setItem(SESSION_IDS_STORAGE, JSON.stringify(next));
}

function sessionFromTimeline(id: string, timeline: TimelineItem[]): Session {
  const messages: Message[] = timeline.flatMap((item) => {
    if (item.kind !== "user_message" && item.kind !== "assistant_message") return [];
    const content = typeof item.payload.content === "string" ? item.payload.content : "";
    // Empty assistant entries represent a model turn that is making tool calls.
    // They are public runtime context, not rendered hidden reasoning.
    if (!content) return [];
    return [
      {
        itemId: item.item_id,
        role: item.kind === "user_message" ? "user" : "assistant",
        content,
        askedAt: item.kind === "user_message" ? item.created_at : undefined,
      },
    ];
  });
  const firstUser = messages.find((message) => message.role === "user");
  const activity = timeline.flatMap((item): ToolActivity[] => {
    if (item.kind === "tool_call" && item.call_id && item.tool_name) {
      return [{ callId: item.call_id, toolName: item.tool_name, status: "started" }];
    }
    if (item.kind === "tool_result" && item.call_id && item.tool_name) {
      const result = item.payload.result as { status?: unknown } | undefined;
      return [
        {
          callId: item.call_id,
          toolName: item.tool_name,
          status: result?.status === "success" ? "completed" : "failed",
        },
      ];
    }
    return [];
  });
  return {
    id,
    title: firstUser ? firstUser.content.slice(0, 60) : "New chat",
    timeline,
    messages,
    activity,
  };
}

function upsertSession(sessions: Session[], next: Session): Session[] {
  return [next, ...sessions.filter((session) => session.id !== next.id)];
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [generatingSessions, setGeneratingSessions] = useState<Set<string>>(new Set());

  const loadSession = useCallback(async (id: string) => {
    const timeline = await apiJson<TimelineItem[]>(
      `/api/sessions/${encodeURIComponent(id)}/timeline`,
    );
    const session = sessionFromTimeline(id, timeline);
    rememberSession(id);
    setSessions((previous) => upsertSession(previous, session));
  }, []);

  useEffect(() => {
    let disposed = false;
    const ids = rememberedSessionIds();
    if (ids.length === 0) return;
    void Promise.all(
      ids.map(async (id) => {
        try {
          const timeline = await apiJson<TimelineItem[]>(
            `/api/sessions/${encodeURIComponent(id)}/timeline`,
          );
          return sessionFromTimeline(id, timeline);
        } catch {
          return null;
        }
      }),
    ).then((loaded) => {
      if (disposed) return;
      const available = loaded.filter((session): session is Session => session !== null);
      setSessions(available);
      setCurrentSessionId(available[0]?.id || null);
    });
    return () => {
      disposed = true;
    };
  }, []);

  const createSession = useCallback(async () => {
    const data = await apiJson<{ session_id: string }>("/api/sessions", { method: "POST" });
    const session = sessionFromTimeline(data.session_id, []);
    rememberSession(data.session_id);
    setSessions((previous) => upsertSession(previous, session));
    setCurrentSessionId(data.session_id);
    return data.session_id;
  }, []);

  const startNewChat = useCallback(() => setCurrentSessionId(null), []);

  const switchSession = useCallback(
    async (id: string) => {
      setCurrentSessionId(id);
      try {
        await loadSession(id);
      } catch {
        // A later submission can surface a clear backend error to the user.
      }
    },
    [loadSession],
  );

  const addOptimisticMessage = useCallback((sessionId: string, content: string) => {
    setSessions((previous) => {
      const current =
        previous.find((session) => session.id === sessionId) || sessionFromTimeline(sessionId, []);
      const message: Message = {
        itemId: `optimistic-user-${Date.now()}`,
        role: "user",
        content,
        askedAt: new Date().toISOString(),
      };
      return upsertSession(previous, {
        ...current,
        title: current.messages.length === 0 ? content.slice(0, 60) : current.title,
        messages: [...current.messages, message],
      });
    });
  }, []);

  const addOptimisticAssistant = useCallback((sessionId: string) => {
    setSessions((previous) => {
      const current = previous.find((session) => session.id === sessionId);
      if (!current) return previous;
      return upsertSession(previous, {
        ...current,
        messages: [
          ...current.messages,
          { itemId: `optimistic-assistant-${Date.now()}`, role: "assistant", content: "" },
        ],
      });
    });
  }, []);

  const appendAssistantDelta = useCallback((sessionId: string, content: string) => {
    if (!content) return;
    setSessions((previous) =>
      previous.map((session) => {
        if (session.id !== sessionId) return session;
        const last = session.messages.at(-1);
        if (last?.role === "assistant" && last.itemId.startsWith("optimistic-assistant-")) {
          return {
            ...session,
            messages: [
              ...session.messages.slice(0, -1),
              { ...last, content: last.content + content },
            ],
          };
        }
        return {
          ...session,
          messages: [
            ...session.messages,
            {
              itemId: `optimistic-assistant-${Date.now()}`,
              role: "assistant",
              content,
            },
          ],
        };
      }),
    );
  }, []);

  const reconcileAssistantMessage = useCallback((sessionId: string, item: TimelineItem) => {
    if (item.kind !== "assistant_message") return;
    const content = typeof item.payload.content === "string" ? item.payload.content : "";
    if (!content) return;
    setSessions((previous) =>
      previous.map((session) => {
        if (session.id !== sessionId) return session;
        const canonical: Message = { itemId: item.item_id, role: "assistant", content };
        const existing = session.messages.findIndex((message) => message.itemId === item.item_id);
        if (existing >= 0) {
          const messages = [...session.messages];
          messages[existing] = canonical;
          return { ...session, messages };
        }
        const last = session.messages.at(-1);
        if (last?.role === "assistant" && last.itemId.startsWith("optimistic-assistant-")) {
          return { ...session, messages: [...session.messages.slice(0, -1), canonical] };
        }
        return { ...session, messages: [...session.messages, canonical] };
      }),
    );
  }, []);

  const recordEvent = useCallback((sessionId: string, event: RuntimeEvent) => {
    if (!event.type.startsWith("tool.")) return;
    const callId = typeof event.payload.call_id === "string" ? event.payload.call_id : "unknown";
    const toolName = typeof event.payload.tool_name === "string" ? event.payload.tool_name : "tool";
    const status =
      event.type === "tool.started"
        ? "started"
        : event.type === "tool.completed"
          ? "completed"
          : "failed";
    setSessions((previous) =>
      previous.map((session) =>
        session.id === sessionId
          ? { ...session, activity: [...session.activity, { callId, toolName, status }] }
          : session,
      ),
    );
  }, []);

  const setSessionGenerating = useCallback((sessionId: string, generating: boolean) => {
    setGeneratingSessions((previous) => {
      const next = new Set(previous);
      if (generating) next.add(sessionId);
      else next.delete(sessionId);
      return next;
    });
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      sessions,
      currentSessionId,
      generatingSessions,
      createSession,
      startNewChat,
      switchSession,
      loadSession,
      addOptimisticMessage,
      addOptimisticAssistant,
      appendAssistantDelta,
      reconcileAssistantMessage,
      recordEvent,
      setSessionGenerating,
    }),
    [
      sessions,
      currentSessionId,
      generatingSessions,
      createSession,
      startNewChat,
      switchSession,
      loadSession,
      addOptimisticMessage,
      addOptimisticAssistant,
      appendAssistantDelta,
      reconcileAssistantMessage,
      recordEvent,
      setSessionGenerating,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
