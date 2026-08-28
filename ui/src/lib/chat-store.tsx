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
  getSessionIdentity,
  listSessions,
  projectDocuments,
  deleteSession as deletePersistedSession,
  renameSession as renamePersistedSession,
  type DocumentRef,
  type DocumentStatus,
  apiJson,
  sessionDocumentStatus,
} from "@/lib/api";

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
  targetRef?: string;
  operationKind?: "read" | "mutation";
  changed?: boolean;
  verification?: string;
  outcomeUnknown?: boolean;
};

export type Message = {
  itemId: string;
  role: "user" | "assistant";
  content: string;
  askedAt?: string;
  citationSourceRefIds?: string[];
  responseTimeMs?: number;
  inputTokens?: number;
  outputTokens?: number;
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
  sourceKind: string;
  documentId: string | null;
  segmentId: string | null;
  page: number | null;
  section: string | null;
  label: string;
  url: string | null;
  retrievedAt: string | null;
};

export type Session = {
  id: string;
  projectId: string | null;
  title: string;
  customTitle?: string | null;
  timeline: TimelineItem[];
  messages: Message[];
  activity: ToolActivity[];
  documents: SessionDocument[];
  sources: SourceReference[];
};

export function sessionRoute(
  session: Pick<Session, "projectId">,
): { to: "/" } | { to: "/projects/$projectId"; params: { projectId: string } } {
  return session.projectId === null
    ? { to: "/" }
    : { to: "/projects/$projectId", params: { projectId: session.projectId } };
}

type ChatContextValue = {
  sessions: Session[];
  sessionsLoaded: boolean;
  currentSessionId: string | null;
  generatingSessions: Set<string>;
  createSession: (projectId?: string) => Promise<string>;
  startNewChat: () => void;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  switchSession: (id: string) => Promise<Session | null>;
  loadSession: (id: string) => Promise<Session>;
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

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function publicActivity(
  callId: string,
  toolName: string,
  status: ToolActivity["status"],
  payload: Record<string, unknown>,
  targetRef?: string,
): ToolActivity {
  return {
    callId,
    toolName,
    status,
    ...(typeof payload.target_ref === "string" || targetRef
      ? { targetRef: typeof payload.target_ref === "string" ? payload.target_ref : targetRef }
      : {}),
    ...(payload.operation_kind === "read" || payload.operation_kind === "mutation"
      ? { operationKind: payload.operation_kind }
      : {}),
    ...(typeof payload.changed === "boolean" ? { changed: payload.changed } : {}),
    ...(typeof payload.verification === "string" ? { verification: payload.verification } : {}),
    ...(payload.outcome_unknown === true ? { outcomeUnknown: true } : {}),
  };
}

export function assistantMessageFromTimelineItem(item: TimelineItem): Message | null {
  if (item.kind !== "assistant_message") return null;
  const content = typeof item.payload.content === "string" ? item.payload.content : "";
  // Tool-call-only turns remain in the canonical timeline, but whitespace is not visible
  // assistant content and must not produce a chat message in the presentation projection.
  if (!content.trim()) return null;
  const metrics = item.payload.metrics;
  const numeric = (key: string) =>
    metrics &&
    typeof metrics === "object" &&
    typeof (metrics as Record<string, unknown>)[key] === "number" &&
    Number.isFinite((metrics as Record<string, number>)[key]) &&
    (metrics as Record<string, number>)[key] >= 0
      ? (metrics as Record<string, number>)[key]
      : undefined;
  return {
    itemId: item.item_id,
    role: "assistant",
    content,
    citationSourceRefIds: stringArray(item.payload.citation_source_ref_ids),
    responseTimeMs: numeric("response_time_ms"),
    inputTokens: numeric("input_tokens"),
    outputTokens: numeric("output_tokens"),
  };
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
        source.source_kind === "internet" &&
        typeof sourceRefId === "string" &&
        typeof source.url === "string" &&
        typeof source.source_id === "string" &&
        source.source_id === source.url
      ) {
        sources.set(sourceRefId, {
          sourceRefId,
          sourceKind: "internet",
          documentId: null,
          segmentId: null,
          page: null,
          section: null,
          label: typeof source.label === "string" ? source.label : source.url,
          url: source.url,
          retrievedAt: typeof source.retrieved_at === "string" ? source.retrieved_at : null,
        });
        continue;
      }
      if (
        (source.source_kind === "linux" ||
          source.source_kind === "grafana" ||
          source.source_kind === "zabbix") &&
        typeof sourceRefId === "string" &&
        typeof source.source_id === "string"
      ) {
        sources.set(sourceRefId, {
          sourceRefId,
          sourceKind: source.source_kind,
          documentId: null,
          segmentId: null,
          page: null,
          section: typeof source.section === "string" ? source.section : null,
          label: typeof source.label === "string" ? source.label : source.source_id,
          url: null,
          retrievedAt: typeof source.retrieved_at === "string" ? source.retrieved_at : null,
        });
        continue;
      }
      if (
        typeof sourceRefId !== "string" ||
        typeof documentId !== "string" ||
        !availableDocuments.has(documentId)
      ) {
        continue;
      }
      const document = availableDocuments.get(documentId)!;
      if (
        source.source_kind !== document.document.source.kind ||
        source.source_id !== document.document.source.source_id
      ) {
        continue;
      }
      sources.set(sourceRefId, {
        sourceRefId,
        sourceKind: document.document.source.kind,
        documentId,
        segmentId: typeof source.segment_id === "string" ? source.segment_id : null,
        page: typeof source.page === "number" ? source.page : null,
        section: typeof source.section === "string" ? source.section : null,
        label: document.document.name,
        url: null,
        retrievedAt: null,
      });
    }
  }
  return [...sources.values()];
}

export function sessionFromTimeline(
  id: string,
  timeline: TimelineItem[],
  documents: SessionDocument[] = attachmentCandidates(timeline),
  projectId: string | null = null,
  customTitle: string | null = null,
): Session {
  const sources = sourceReferences(timeline, documents);
  const availableSourceIds = new Set(sources.map((source) => source.sourceRefId));
  const messages: Message[] = timeline.flatMap((item): Message[] => {
    if (item.kind !== "user_message" && item.kind !== "assistant_message") return [];
    const content = typeof item.payload.content === "string" ? item.payload.content : "";
    // Empty assistant entries represent a model turn that is making tool calls.
    // They are public runtime context, not rendered hidden reasoning.
    if (!content) return [];
    if (item.kind === "user_message") {
      return [{ itemId: item.item_id, role: "user" as const, content, askedAt: item.created_at }];
    }
    const assistant = assistantMessageFromTimelineItem(item);
    return assistant
      ? [
          {
            ...assistant,
            citationSourceRefIds: assistant.citationSourceRefIds?.filter((id) =>
              availableSourceIds.has(id),
            ),
          },
        ]
      : [];
  });
  const firstUser = messages.find((message) => message.role === "user");
  const callMetadata = new Map<
    string,
    { targetRef?: string; operationKind?: "read" | "mutation" }
  >();
  for (const item of timeline) {
    const targetRef =
      item.payload.arguments && typeof item.payload.arguments === "object"
        ? (item.payload.arguments as Record<string, unknown>).target_ref
        : undefined;
    if (item.kind === "tool_call" && item.call_id) {
      callMetadata.set(item.call_id, {
        ...(typeof targetRef === "string" ? { targetRef } : {}),
        ...(item.payload.operation_kind === "read" || item.payload.operation_kind === "mutation"
          ? { operationKind: item.payload.operation_kind }
          : {}),
      });
    }
  }
  const activityByCallId = new Map<string, ToolActivity>();
  for (const item of timeline) {
    if (item.kind === "tool_call" && item.call_id && item.tool_name) {
      const metadata = callMetadata.get(item.call_id);
      activityByCallId.set(
        item.call_id,
        publicActivity(
          item.call_id,
          item.tool_name,
          "started",
          {
            target_ref: metadata?.targetRef,
            operation_kind: metadata?.operationKind,
          },
          metadata?.targetRef,
        ),
      );
    }
    if (item.kind === "tool_result" && item.call_id && item.tool_name) {
      const result = item.payload.result as
        { status?: unknown; data?: unknown; error?: unknown } | undefined;
      const data =
        result?.data && typeof result.data === "object"
          ? (result.data as Record<string, unknown>)
          : {};
      const error =
        result?.error && typeof result.error === "object"
          ? (result.error as Record<string, unknown>)
          : {};
      activityByCallId.set(
        item.call_id,
        publicActivity(
          item.call_id,
          item.tool_name,
          result?.status === "success" ? "completed" : "failed",
          {
            operation_kind: callMetadata.get(item.call_id)?.operationKind,
            target_ref: data.target_ref,
            changed: data.changed,
            verification:
              data.verification && typeof data.verification === "object"
                ? (data.verification as Record<string, unknown>).status
                : undefined,
            outcome_unknown: error.code === "outcome_unknown",
          },
          callMetadata.get(item.call_id)?.targetRef,
        ),
      );
    }
  }
  const activity = [...activityByCallId.values()];
  return {
    id,
    projectId,
    title: customTitle ?? (firstUser ? firstUser.content.slice(0, 60) : "New chat"),
    customTitle,
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
  projectId: string | null,
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
  const sessionDocuments = resolved.filter(
    (document): document is SessionDocument => document !== null,
  );
  if (projectId === null) return sessionDocuments;
  const project = await projectDocuments(projectId);
  return [
    ...sessionDocuments,
    ...project
      .filter((document) => !document.deleted)
      .map(
        (document) =>
          ({
            document: document.document,
            attachmentId: document.attachment_id,
            status: document.status,
            errorMessage: document.error_message,
            ingestion: document.ingestion || [],
          }) satisfies SessionDocument,
      ),
  ];
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [generatingSessions, setGeneratingSessions] = useState<Set<string>>(new Set());

  const loadSession = useCallback(async (id: string) => {
    const [identity, timeline] = await Promise.all([
      getSessionIdentity(id),
      apiJson<TimelineItem[]>(`/api/sessions/${encodeURIComponent(id)}/timeline`),
    ]);
    const projectId = identity.project_id ?? null;
    const documents = await reconcileSessionDocuments(id, timeline, projectId);
    const session = sessionFromTimeline(
      id,
      timeline,
      documents,
      projectId,
      identity.custom_title ?? null,
    );
    setSessions((previous) => upsertSession(previous, session));
    return session;
  }, []);

  useEffect(() => {
    let disposed = false;
    void listSessions()
      .then((summaries) => {
        if (disposed) return;
        setSessions(
          summaries.map((summary) => ({
            id: summary.session_id,
            projectId: summary.project_id,
            title: summary.title,
            customTitle: summary.custom_title ?? null,
            timeline: [],
            messages: [],
            activity: [],
            documents: [],
            sources: [],
          })),
        );
        setSessionsLoaded(true);
      })
      .catch(() => {
        if (!disposed) {
          setSessions([]);
          setSessionsLoaded(true);
        }
      });
    return () => {
      disposed = true;
    };
  }, []);

  const createSession = useCallback(async (projectId?: string) => {
    const data = await apiJson<{ session_id: string; project_id: string | null }>(
      projectId ? `/api/projects/${encodeURIComponent(projectId)}/sessions` : "/api/sessions",
      { method: "POST" },
    );
    const session = sessionFromTimeline(data.session_id, [], [], data.project_id ?? null, null);
    setSessions((previous) => upsertSession(previous, session));
    setCurrentSessionId(data.session_id);
    return data.session_id;
  }, []);

  const startNewChat = useCallback(() => setCurrentSessionId(null), []);

  const renameSession = useCallback(async (sessionId: string, title: string) => {
    const updated = await renamePersistedSession(sessionId, title);
    setSessions((previous) =>
      previous.map((session) =>
        session.id === sessionId
          ? { ...session, title: updated.title, customTitle: updated.custom_title }
          : session,
      ),
    );
  }, []);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      const deleted = sessions.find((session) => session.id === sessionId);
      await deletePersistedSession(sessionId);
      const remaining = sessions.filter((session) => session.id !== sessionId);
      const replacement =
        deleted?.projectId === null
          ? null
          : (remaining.find((session) => session.projectId === deleted?.projectId) ?? null);
      setSessions(remaining);
      setGeneratingSessions((previous) => {
        const next = new Set(previous);
        next.delete(sessionId);
        return next;
      });
      if (currentSessionId === sessionId) {
        setCurrentSessionId(replacement?.id ?? null);
        if (replacement) void loadSession(replacement.id);
      }
    },
    [currentSessionId, loadSession, sessions],
  );

  const switchSession = useCallback(
    async (id: string) => {
      setCurrentSessionId(id);
      try {
        return await loadSession(id);
      } catch {
        // A later submission can surface a clear backend error to the user.
        return null;
      }
    },
    [loadSession],
  );

  const addOptimisticMessage = useCallback((sessionId: string, content: string) => {
    setSessions((previous) => {
      const current = previous.find((session) => session.id === sessionId);
      if (!current) return previous;
      const message: Message = {
        itemId: `optimistic-user-${Date.now()}`,
        role: "user",
        content,
        askedAt: new Date().toISOString(),
      };
      return upsertSession(previous, {
        ...current,
        title:
          current.customTitle == null && current.messages.length === 0
            ? content.slice(0, 60)
            : current.title,
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
    const canonical = assistantMessageFromTimelineItem(item);
    if (canonical === null) {
      setSessions((previous) =>
        previous.map((session) => {
          if (session.id !== sessionId) return session;
          const last = session.messages.at(-1);
          if (
            last?.role === "assistant" &&
            last.itemId.startsWith("optimistic-assistant-") &&
            !last.content.trim()
          ) {
            return { ...session, messages: session.messages.slice(0, -1) };
          }
          return session;
        }),
      );
      return;
    }
    setSessions((previous) =>
      previous.map((session) => {
        if (session.id !== sessionId) return session;
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
        session.id !== sessionId
          ? session
          : (() => {
              const existing = session.activity.find((activity) => activity.callId === callId);
              const next = publicActivity(callId, toolName, status, event.payload);
              return {
                ...session,
                activity: [
                  ...session.activity.filter((activity) => activity.callId !== callId),
                  { ...existing, ...next },
                ],
              };
            })(),
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
          return { ...session, documents, sources: sourceReferences(session.timeline, documents) };
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
      sessionsLoaded,
      currentSessionId,
      generatingSessions,
      createSession,
      startNewChat,
      renameSession,
      deleteSession,
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
      sessionsLoaded,
      currentSessionId,
      generatingSessions,
      createSession,
      startNewChat,
      renameSession,
      deleteSession,
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
