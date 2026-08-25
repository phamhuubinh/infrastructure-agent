import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  attachSessionDocument,
  deleteSessionDocument,
  type DocumentRef,
  type DocumentStatus,
  apiJson,
  sessionDocumentStatus,
} from "@/lib/api";

const SESSION_IDS_STORAGE = "orion-m1-session-ids";

export type TimelineKind =
  | "user_message"
  | "assistant_message"
  | "tool_call"
  | "tool_result"
  | "attachment"
  | "runtime_notice";

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
  citationSourceRefIds?: string[];
};

export type SessionDocument = {
  document: DocumentRef;
  attachmentId: string;
  status: DocumentStatus["status"];
  errorMessage: string | null;
  ingestion: NonNullable<DocumentStatus["ingestion"]>;
};

export type SourceReference = {
  sourceRefId: string;
  documentId: string;
  segmentId: string | null;
  page: number | null;
  section: string | null;
  label: string;
};

export type Session = {
  id: string;
  title: string;
  timeline: TimelineItem[];
  messages: Message[];
  activity: ToolActivity[];
  documents: SessionDocument[];
  sources: SourceReference[];
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
  attachDocument: (
    sessionId: string,
    attachment: { name: string; content: string; mediaType: string | null },
  ) => Promise<void>;
  deleteDocument: (sessionId: string, documentId: string) => Promise<void>;
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

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function attachmentCandidates(timeline: TimelineItem[]): SessionDocument[] {
  const documents = new Map<string, SessionDocument>();
  for (const item of timeline) {
    if (item.kind !== "attachment") continue;
    const document = item.payload.document as Partial<DocumentRef> | undefined;
    const attachmentId = item.payload.attachment_id;
    if (
      !document ||
      typeof document.document_id !== "string" ||
      typeof document.name !== "string" ||
      !document.source ||
      typeof attachmentId !== "string"
    ) {
      continue;
    }
    documents.set(document.document_id, {
      document: document as DocumentRef,
      attachmentId,
      status: item.payload.status === "failed" ? "failed" : "uploaded",
      errorMessage: null,
      ingestion: [],
    });
  }
  return [...documents.values()];
}

function sourceReferences(
  sessionId: string,
  timeline: TimelineItem[],
  documents: SessionDocument[],
): SourceReference[] {
  const availableDocuments = new Map(
    documents
      .filter((document) => document.status === "ready")
      .map((document) => [document.document.document_id, document]),
  );
  const sources = new Map<string, SourceReference>();
  for (const item of timeline) {
    if (item.kind !== "tool_result") continue;
    const result = item.payload.result as { status?: unknown; sources?: unknown } | undefined;
    if (result?.status !== "success" || !Array.isArray(result.sources)) continue;
    for (const rawSource of result.sources) {
      if (!rawSource || typeof rawSource !== "object") continue;
      const source = rawSource as Record<string, unknown>;
      const sourceRefId = source.source_ref_id;
      const documentId = source.document_id;
      if (
        typeof sourceRefId !== "string" ||
        typeof documentId !== "string" ||
        source.source_kind !== "session" ||
        source.source_id !== sessionId ||
        !availableDocuments.has(documentId)
      ) {
        continue;
      }
      const document = availableDocuments.get(documentId)!;
      sources.set(sourceRefId, {
        sourceRefId,
        documentId,
        segmentId: typeof source.segment_id === "string" ? source.segment_id : null,
        page: typeof source.page === "number" ? source.page : null,
        section: typeof source.section === "string" ? source.section : null,
        label: document.document.name,
      });
    }
  }
  return [...sources.values()];
}

export function sessionFromTimeline(
  id: string,
  timeline: TimelineItem[],
  documents: SessionDocument[] = attachmentCandidates(timeline),
): Session {
  const sources = sourceReferences(id, timeline, documents);
  const availableSourceIds = new Set(sources.map((source) => source.sourceRefId));
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
        citationSourceRefIds:
          item.kind === "assistant_message"
            ? stringArray(item.payload.citation_source_ref_ids).filter((id) =>
                availableSourceIds.has(id),
              )
            : undefined,
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
    documents,
    sources,
  };
}

function upsertSession(sessions: Session[], next: Session): Session[] {
  return [next, ...sessions.filter((session) => session.id !== next.id)];
}

async function reconcileSessionDocuments(
  sessionId: string,
  timeline: TimelineItem[],
): Promise<SessionDocument[]> {
  const candidates = attachmentCandidates(timeline);
  const resolved = await Promise.all(
    candidates.map(async (candidate) => {
      const status = await sessionDocumentStatus(sessionId, candidate.document.document_id);
      if (status === null || status.deleted) return null;
      return {
        document: status.document,
        attachmentId: status.attachment_id,
        status: status.status,
        errorMessage: status.error_message,
        ingestion: status.ingestion || [],
      } satisfies SessionDocument;
    }),
  );
  return resolved.filter((document): document is SessionDocument => document !== null);
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [generatingSessions, setGeneratingSessions] = useState<Set<string>>(new Set());

  const loadSession = useCallback(async (id: string) => {
    const timeline = await apiJson<TimelineItem[]>(
      `/api/sessions/${encodeURIComponent(id)}/timeline`,
    );
    const documents = await reconcileSessionDocuments(id, timeline);
    const session = sessionFromTimeline(id, timeline, documents);
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
          const documents = await reconcileSessionDocuments(id, timeline);
          return sessionFromTimeline(id, timeline, documents);
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

  const reconcileDocumentStatus = useCallback(
    (sessionId: string, documentId: string, status: DocumentStatus | null) => {
      setSessions((previous) =>
        previous.map((session) => {
          if (session.id !== sessionId) return session;
          const documents =
            status === null || status.deleted
              ? session.documents.filter((document) => document.document.document_id !== documentId)
              : session.documents.map((document) =>
                  document.document.document_id === documentId
                    ? {
                        document: status.document,
                        attachmentId: status.attachment_id,
                        status: status.status,
                        errorMessage: status.error_message,
                        ingestion: status.ingestion || [],
                      }
                    : document,
                );
          return sessionFromTimeline(sessionId, session.timeline, documents);
        }),
      );
    },
    [],
  );

  const pollDocumentStatus = useCallback(
    (sessionId: string, documentId: string) => {
      const poll = async () => {
        try {
          const status = await sessionDocumentStatus(sessionId, documentId);
          reconcileDocumentStatus(sessionId, documentId, status);
          if (status && !status.deleted && !["ready", "failed"].includes(status.status)) {
            window.setTimeout(() => void poll(), 600);
            return;
          }
          if (status?.status === "ready") await loadSession(sessionId);
        } catch {
          // The initial attachment response remains visible; upload errors are handled by the caller.
        }
      };
      void poll();
    },
    [loadSession, reconcileDocumentStatus],
  );

  const attachDocument = useCallback(
    async (
      sessionId: string,
      attachment: { name: string; content: string; mediaType: string | null },
    ) => {
      const uploaded = await attachSessionDocument(sessionId, {
        name: attachment.name,
        content: attachment.content,
        media_type: attachment.mediaType,
      });
      const document: SessionDocument = {
        document: uploaded.document,
        attachmentId: uploaded.attachment_id,
        status: uploaded.status,
        errorMessage: uploaded.error_message,
        ingestion: [],
      };
      setSessions((previous) =>
        previous.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                documents: [
                  document,
                  ...session.documents.filter(
                    (known) => known.document.document_id !== document.document.document_id,
                  ),
                ],
              }
            : session,
        ),
      );
      if (["ready", "failed"].includes(uploaded.status)) await loadSession(sessionId);
      else pollDocumentStatus(sessionId, uploaded.document.document_id);
    },
    [loadSession, pollDocumentStatus],
  );

  const deleteDocument = useCallback(
    async (sessionId: string, documentId: string) => {
      await deleteSessionDocument(sessionId, documentId);
      setSessions((previous) =>
        previous.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                documents: session.documents.filter(
                  (document) => document.document.document_id !== documentId,
                ),
                sources: session.sources.filter((source) => source.documentId !== documentId),
                messages: session.messages.map((message) => ({
                  ...message,
                  citationSourceRefIds: message.citationSourceRefIds?.filter(
                    (sourceRefId) =>
                      !session.sources.some(
                        (source) =>
                          source.sourceRefId === sourceRefId && source.documentId === documentId,
                      ),
                  ),
                })),
              }
            : session,
        ),
      );
      await loadSession(sessionId);
    },
    [loadSession],
  );

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
      attachDocument,
      deleteDocument,
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
      attachDocument,
      deleteDocument,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
