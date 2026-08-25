export const API_URL = import.meta.env.VITE_API_URL || "";

const PUBLIC_SECRET_MARKERS = [
  "ORION_TEST_SECRET_TOKEN",
  "ORION_TEST_PRIVATE_URL",
  "/private/test/key",
];

export function redactPublicText(value: string): string {
  return PUBLIC_SECRET_MARKERS.reduce(
    (result, marker) => result.replaceAll(marker, "[REDACTED]"),
    value,
  );
}

export type DocumentRef = {
  document_id: string;
  source: { kind: "session" | "project" | "shared"; source_id: string };
  name: string;
  media_type: string | null;
};

export type DocumentStatus = {
  document: DocumentRef;
  attachment_id: string;
  status: "uploaded" | "parsing" | "indexing" | "ready" | "failed";
  error_message: string | null;
  deleted?: boolean;
  ingestion?: Array<{ state: string; error_message: string | null; created_at: string }>;
};

export type AttachmentResponse = Pick<
  DocumentStatus,
  "document" | "attachment_id" | "status" | "error_message"
>;

export type Project = {
  project_id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProjectInput = Pick<Project, "name" | "description" | "instructions" | "metadata">;

export type SessionIdentity = {
  session_id: string;
  project_id: string | null;
};

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export async function apiErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  let message = body;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") message = parsed.detail;
    else if (parsed.detail) message = JSON.stringify(parsed.detail);
  } catch {
    // Keep non-JSON upstream error text.
  }

  return redactPublicText(message || `Request failed (${response.status})`);
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response));
  }
  return (await response.json()) as T;
}

export async function attachSessionDocument(
  sessionId: string,
  attachment: { name: string; content: string; media_type: string | null },
): Promise<AttachmentResponse> {
  return apiJson<AttachmentResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/attachments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(attachment),
  });
}

/** A missing status is the canonical tombstone/reload reconciliation signal. */
export async function sessionDocumentStatus(
  sessionId: string,
  documentId: string,
): Promise<DocumentStatus | null> {
  const response = await apiFetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await apiErrorMessage(response));
  return (await response.json()) as DocumentStatus;
}

export async function deleteSessionDocument(sessionId: string, documentId: string): Promise<void> {
  const response = await apiFetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await apiErrorMessage(response));
}

export async function getSessionIdentity(sessionId: string): Promise<SessionIdentity> {
  return apiJson<SessionIdentity>(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export async function listProjects(): Promise<Project[]> {
  return apiJson<Project[]>("/api/projects");
}

export async function createProject(project: ProjectInput): Promise<Project> {
  return apiJson<Project>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
}

export async function getProject(projectId: string): Promise<Project> {
  return apiJson<Project>(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function projectDocuments(projectId: string): Promise<DocumentStatus[]> {
  return apiJson<DocumentStatus[]>(`/api/projects/${encodeURIComponent(projectId)}/documents`);
}

export async function attachProjectDocument(
  projectId: string,
  attachment: { name: string; content: string; media_type: string | null },
): Promise<AttachmentResponse> {
  return apiJson<AttachmentResponse>(`/api/projects/${encodeURIComponent(projectId)}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(attachment),
  });
}

export async function deleteProjectDocument(projectId: string, documentId: string): Promise<void> {
  const response = await apiFetch(
    `/api/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await apiErrorMessage(response));
}
