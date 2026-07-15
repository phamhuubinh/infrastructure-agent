import { createContext, useContext, useState, useRef, type ReactNode } from "react";

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

  const value: ChatContextValue = {
    sessions,
    currentSessionId,
    createSession() {
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
    },
    switchSession(id: string) {
      setCurrentSessionId(id);
      currentIdRef.current = id;
    },
    getSession() {
      return sessionsRef.current.find((s) => s.id === currentIdRef.current);
    },
    updateSession(updates: Partial<Session>) {
      const id = currentIdRef.current;
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, ...updates } : s)),
      );
    },
    deleteSession(id: string) {
      setSessions((prev) => {
        const next = prev.filter((s) => s.id !== id);
        if (currentSessionId === id && next.length > 0) {
          setCurrentSessionId(next[0].id);
        } else if (next.length === 0) {
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
    },
    renameSession(id: string, title: string) {
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    },
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
