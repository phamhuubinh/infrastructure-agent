import {
  createContext,
  useContext,
  useState,
  useRef,
  useMemo,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { apiFetch, apiJson } from "@/lib/api";

export type Step = {
  type: string;
  intent?: string;
  confidence?: string;
  target?: string;
  matched_keywords?: string[];
  required_evidence?: string[];
  optional_evidence?: string[];
  planned_capabilities?: { capability: string; evidence: string }[];
  collected?: number;
  successful?: number;
  failed?: number;
  items?: {
    capability: string;
    evidence: string;
    success: boolean;
    error?: string | null;
    data_preview?: string | null;
    data?: unknown;
  }[];
  complete?: boolean;
  missing_evidence?: string[];
  runtime_metrics?: {
    execution_duration: number;
    total_nodes: number;
    successful_nodes: number;
    failed_nodes: number;
    parallel_ratio: number;
    tool_calls: number;
  };
  size?: number;
  preview?: string;
  model?: string;
  latency_ms?: number;
  success?: boolean;
  error?: string | null;
  content?: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  steps?: Step[];
  responseTimeMs?: number;
  askedAt?: string;
};

export type Session = {
  id: string;
  title: string;
  messages: Message[];
};

type ChatContextValue = {
  sessions: Session[];
  currentSessionId: string | null;
  generatingSessions: Set<string>;
  setSessionGenerating: (sessionId: string, generating: boolean) => void;
  createSession: () => Promise<string>;
  startNewChat: () => void;
  switchSession: (id: string) => void;
  getSession: () => Session | undefined;
  updateSession: (updates: Partial<Session>) => void;
  updateSessionById: (id: string, updates: Partial<Session>) => void;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
};

const ChatContext = createContext<ChatContextValue>(null!);

export function useChat() {
  return useContext(ChatContext);
}

function emptySession(id: string, title: string = "New chat", msgs: Message[] = []): Session {
  return {
    id,
    title,
    messages: msgs.map((message) => {
      const storedMessage = message as Message & { response_time_ms?: number; asked_at?: string };
      return {
        ...message,
        responseTimeMs: message.responseTimeMs ?? storedMessage.response_time_ms,
        askedAt: message.askedAt ?? storedMessage.asked_at,
      };
    }),
  };
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [generatingSessions, setGeneratingSessions] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const sessionsRef = useRef(sessions);
  const currentIdRef = useRef(currentSessionId);
  sessionsRef.current = sessions;
  currentIdRef.current = currentSessionId;

  // Load sessions from backend on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiFetch("/api/sessions");
        if (!res.ok) throw new Error("failed");
        const data = await res.json();
        if (cancelled) return;
        const serverSessions: Session[] = (data.sessions || [])
          .map((s: { id: string; title?: string; messages?: Message[] }) =>
            emptySession(s.id, s.title || "New chat", s.messages || []),
          )
          .filter((session: Session) => session.messages.length > 0);
        if (serverSessions.length > 0) {
          setSessions(serverSessions);
          setCurrentSessionId(serverSessions[0].id);
          currentIdRef.current = serverSessions[0].id;
        } else {
          // No sessions on server — leave empty, user will create one
          setSessions([]);
          setCurrentSessionId(null);
        }
      } catch {
        // Server not available — keep the unsaved draft screen available.
        if (cancelled) return;
        sessionsRef.current = [];
        setSessions([]);
        setCurrentSessionId(null);
        currentIdRef.current = null;
      }
      setLoaded(true);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const setSessionGenerating = useCallback((sessionId: string, generating: boolean) => {
    setGeneratingSessions((prev) => {
      const next = new Set(prev);
      if (generating) {
        next.add(sessionId);
      } else {
        next.delete(sessionId);
      }
      return next;
    });
  }, []);

  const createSession = useCallback(async () => {
    let sessionId: string;
    try {
      const data = await apiJson<{ session_id: string }>("/api/sessions", {
        method: "POST",
      });
      sessionId = data.session_id;
    } catch {
      sessionId = `local_${Date.now().toString(36)}`;
    }

    const newSession = emptySession(sessionId);
    const nextSessions = [newSession, ...sessionsRef.current];
    sessionsRef.current = nextSessions;
    setSessions(nextSessions);
    setCurrentSessionId(sessionId);
    currentIdRef.current = sessionId;
    return sessionId;
  }, []);

  const startNewChat = useCallback(() => {
    setCurrentSessionId(null);
    currentIdRef.current = null;
  }, []);

  const switchSession = useCallback((id: string) => {
    setCurrentSessionId(id);
    currentIdRef.current = id;
  }, []);

  const getSession = useCallback(() => {
    return sessionsRef.current.find((s) => s.id === currentIdRef.current);
  }, []);

  const updateSession = useCallback((updates: Partial<Session>) => {
    const id = currentIdRef.current;
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }, []);

  const updateSessionById = useCallback((id: string, updates: Partial<Session>) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    try {
      await apiFetch(`/api/sessions/${id}`, { method: "DELETE" });
    } catch {
      // server not available, delete locally anyway
    }
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      sessionsRef.current = next;
      if (next.length > 0) {
        if (currentIdRef.current === id) {
          setCurrentSessionId(next[0].id);
          currentIdRef.current = next[0].id;
        }
      } else {
        setCurrentSessionId(null);
        currentIdRef.current = null;
      }
      return next;
    });
    // Clean up generating state
    setGeneratingSessions((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const renameSession = useCallback(async (id: string, title: string) => {
    try {
      await apiFetch(`/api/sessions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
    } catch {
      // server not available
    }
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      sessions,
      currentSessionId,
      generatingSessions,
      setSessionGenerating,
      createSession,
      startNewChat,
      switchSession,
      getSession,
      updateSession,
      updateSessionById,
      deleteSession,
      renameSession,
    }),
    [
      sessions,
      currentSessionId,
      generatingSessions,
      setSessionGenerating,
      createSession,
      startNewChat,
      switchSession,
      getSession,
      updateSession,
      updateSessionById,
      deleteSession,
      renameSession,
    ],
  );

  if (!loaded) {
    return <ChatContext.Provider value={value}>{null}</ChatContext.Provider>;
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
