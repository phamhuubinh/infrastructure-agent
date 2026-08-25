import { createFileRoute } from "@tanstack/react-router";
import { FileText, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatPage } from "@/routes/index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  attachProjectDocument,
  deleteProjectDocument,
  getProject,
  projectDocumentStatus,
  projectDocuments,
  updateProject,
  type DocumentStatus,
  type Project,
} from "@/lib/api";
import { useChat } from "@/lib/chat-store";

export const Route = createFileRoute("/projects/$projectId")({ component: ProjectWorkspace });

function ProjectWorkspace() {
  const { projectId } = Route.useParams();
  const chat = useChat();
  const fileInput = useRef<HTMLInputElement>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [documents, setDocuments] = useState<DocumentStatus[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError(null);
    void Promise.all([getProject(projectId), projectDocuments(projectId)])
      .then(([loadedProject, loadedDocuments]) => {
        if (disposed) return;
        setProject(loadedProject);
        setDocuments(loadedDocuments);
        setName(loadedProject.name);
        setDescription(loadedProject.description || "");
        setInstructions(loadedProject.instructions || "");
      })
      .catch((reason: unknown) => {
        if (!disposed)
          setError(reason instanceof Error ? reason.message : "Unable to load project.");
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [projectId]);

  useEffect(() => {
    const pending = documents.filter(
      (document) =>
        document.status === "uploaded" ||
        document.status === "parsing" ||
        document.status === "indexing",
    );
    if (pending.length === 0) return;
    const timer = window.setTimeout(() => {
      void Promise.all(
        pending.map((document) => projectDocumentStatus(projectId, document.document.document_id)),
      )
        .then((statuses) => {
          setDocuments((current) =>
            current.flatMap((document) => {
              const next = statuses.find(
                (status) => status?.document.document_id === document.document.document_id,
              );
              return next ? [next] : [document];
            }),
          );
        })
        .catch(() => undefined);
    }, 600);
    return () => window.clearTimeout(timer);
  }, [documents, projectId]);

  async function saveMetadata() {
    if (!project || !name.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateProject(project.project_id, {
        name: name.trim(),
        description: description.trim() || null,
        instructions: instructions.trim() || null,
        metadata: project.metadata,
      });
      setProject(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save project.");
    } finally {
      setSaving(false);
    }
  }

  async function uploadDocument(file: File) {
    if (!project || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await attachProjectDocument(project.project_id, {
        name: file.name,
        content: await file.text(),
        media_type: file.type || "text/plain",
      });
      setDocuments((current) => [...current, { ...uploaded, ingestion: [], deleted: false }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to upload document.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function removeDocument(documentId: string) {
    if (!project) return;
    setError(null);
    try {
      await deleteProjectDocument(project.project_id, documentId);
      setDocuments((current) =>
        current.filter((document) => document.document.document_id !== documentId),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete document.");
    }
  }

  const conversations = chat.sessions.filter((session) => session.projectId === projectId);

  if (loading) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin" />
      </main>
    );
  }
  if (!project) {
    return (
      <main className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        {error || "Project not found."}
      </main>
    );
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="border-b border-border bg-background px-4 py-4 sm:px-6">
        <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <Card className="p-4">
            <div className="flex gap-2">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                aria-label="Project name"
              />
              <Button
                onClick={() => void saveMetadata()}
                disabled={!name.trim() || saving}
                size="sm"
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Save
              </Button>
            </div>
            <Input
              className="mt-2"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Description"
              aria-label="Project description"
            />
            <Textarea
              className="mt-2 min-h-16"
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="Project instructions for Orion"
              aria-label="Project instructions"
            />
          </Card>
          <Card className="p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="font-medium">Project documents</div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => fileInput.current?.click()}
                disabled={uploading}
              >
                <Plus className="h-4 w-4" /> Add
              </Button>
            </div>
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void uploadDocument(file);
              }}
            />
            <div className="mt-3 max-h-32 space-y-2 overflow-y-auto text-sm">
              {documents.length === 0 ? (
                <div className="text-muted-foreground">No project documents yet.</div>
              ) : (
                documents.map((document) => (
                  <div key={document.document.document_id} className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{document.document.name}</span>
                    <span className="text-xs text-muted-foreground">{document.status}</span>
                    <button
                      type="button"
                      aria-label={`Delete ${document.document.name}`}
                      onClick={() => void removeDocument(document.document.document_id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
        <div className="mx-auto mt-3 flex max-w-6xl items-center gap-2 text-sm">
          <span className="text-muted-foreground">Project conversations:</span>
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              className="max-w-40 truncate rounded border border-border px-2 py-1 hover:bg-accent"
              onClick={() => void chat.switchSession(conversation.id)}
            >
              {conversation.title}
            </button>
          ))}
          <Button size="sm" variant="outline" onClick={() => void chat.createSession(projectId)}>
            <Plus className="h-4 w-4" /> New conversation
          </Button>
        </div>
        {error && (
          <div role="alert" className="mx-auto mt-2 max-w-6xl text-sm text-destructive">
            {error}
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-1">
        <ChatPage project={project} />
      </div>
    </main>
  );
}
