import {
  createContext,
  useContext,
  useState,
  useRef,
  useMemo,
  useCallback,
  type ReactNode,
} from "react";

const API_URL = import.meta.env.VITE_API_URL || "";

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
};

export type Session = {
  id: string;
  title: string;
  messages: Message[];
};

type ChatContextValue = {
  sessions: Session[];
  currentSessionId: string | null;
  createSession: () => string;
  switchSession: (id: string) => void;
  getSession: () => Session | undefined;
  updateSession: (updates: Partial<Session>) => void;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
};

const ChatContext = createContext<ChatContextValue>(null!);

export function useChat() {
  return useContext(ChatContext);
}

let nextId = 1;

function genId() {
  return `sess_${nextId++}_${Date.now().toString(36)}`;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>(() => [
    {
      id: genId(),
      title: "New chat",
      messages: [
        {
          role: "assistant",
          content: "Gõ câu hỏi để bắt đầu điều tra hạ tầng.",
        },
      ],
    },
  ]);
  const [currentSessionId, setCurrentSessionId] = useState(sessions[0].id);
  const sessionsRef = useRef(sessions);
  const currentIdRef = useRef(currentSessionId);
  sessionsRef.current = sessions;
  currentIdRef.current = currentSessionId;

  const createSession = useCallback(() => {
    const id = genId();
    setSessions((prev) => [
      ...prev,
      {
        id,
        title: "New chat",
        messages: [
          {
            role: "assistant",
            content: "Gõ câu hỏi để bắt đầu điều tra hạ tầng.",
          },
        ],
      },
    ]);
    setCurrentSessionId(id);
    currentIdRef.current = id;
    return id;
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

  const deleteSession = useCallback(async (id: string) => {
    try {
      await fetch(`${API_URL}/api/sessions/${id}`, { method: "DELETE" });
    } catch {
      // server not available, delete locally anyway
    }
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (next.length > 0) {
        if (currentIdRef.current === id) {
          setCurrentSessionId(next[0].id);
        }
      } else {
        const fresh = genId();
        setCurrentSessionId(fresh);
        return [
          {
            id: fresh,
            title: "New chat",
            messages: [
              {
                role: "assistant",
                content: "Gõ câu hỏi để bắt đầu điều tra hạ tầng.",
              },
            ],
          },
        ];
      }
      return next;
    });
  }, []);

  const renameSession = useCallback(async (id: string, title: string) => {
    try {
      await fetch(`${API_URL}/api/sessions/${id}`, {
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
      createSession,
      switchSession,
      getSession,
      updateSession,
      deleteSession,
      renameSession,
    }),
    [
      sessions,
      currentSessionId,
      createSession,
      switchSession,
      getSession,
      updateSession,
      deleteSession,
      renameSession,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
