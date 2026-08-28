import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FileText, FolderKanban, Loader2, Plus, Save, Settings2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatPage } from "@/routes/index";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import {
  attachProjectDocument,
  deleteProject,
  deleteProjectDocument,
  getProject,
  projectDocumentStatus,
  projectDocuments,
  updateProject,
  type DocumentStatus,
  type Project,
} from "@/lib/api";
import { useChat } from "@/lib/chat-store";
import { invalidateProjectList } from "@/lib/project-list";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export const Route = createFileRoute("/projects/$projectId")({ component: ProjectWorkspaceRoute });

function ProjectWorkspaceRoute() {
  return <ProjectWorkspace projectId={Route.useParams().projectId} />;
}

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const chat = useChat();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [documents, setDocuments] = useState<DocumentStatus[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
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
        if (!disposed) {
          setError(reason instanceof Error ? reason.message : "Unable to load project.");
        }
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [projectId]);

  useEffect(() => {
    const pending = documents.filter((document) =>
      ["uploaded", "parsing", "indexing"].includes(document.status),
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
      invalidateProjectList();
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

  async function removeProject() {
    if (!project || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteProject(project.project_id);
      chat.removeProjectSessions(project.project_id);
      invalidateProjectList();
      setDeleteConfirmationOpen(false);
      setDetailsOpen(false);
      await navigate({ to: "/projects" });
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Không thể xóa Project. Hãy hoàn tất hoặc hủy hội thoại đang chạy.",
      );
    } finally {
      setDeleting(false);
    }
  }

  function newConversation() {
    chat.startNewChat();
  }

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
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-background px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-border bg-surface-2">
            <FolderKanban className="h-4 w-4 text-titanium" />
          </div>
          <h1 className="truncate text-base font-semibold">{project.name}</h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setDetailsOpen(true)}>
            <Settings2 className="h-4 w-4" /> Chi tiết
          </Button>
          <Button size="sm" onClick={newConversation}>
            <Plus className="h-4 w-4" /> Hội thoại mới
          </Button>
        </div>
      </header>
      {error && (
        <div role="alert" className="px-4 pt-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <ChatPage project={project} />
      </div>
      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent className="flex w-full flex-col sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Chi tiết Project</SheetTitle>
            <SheetDescription>
              Thông tin và tài liệu này được chia sẻ bởi mọi hội thoại trong Project.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-5 flex-1 space-y-5 overflow-y-auto pr-1">
            <section className="space-y-3">
              <div className="text-sm font-medium">Thông tin</div>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                aria-label="Project name"
              />
              <Input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Description"
                aria-label="Project description"
              />
              <Textarea
                className="min-h-24"
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                placeholder="Project instructions for Orion"
                aria-label="Project instructions"
              />
              <Button
                className="w-full"
                onClick={() => void saveMetadata()}
                disabled={!name.trim() || saving}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Lưu thay đổi
              </Button>
            </section>
            <section className="border-t border-border pt-5">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium">Tài liệu Project</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Dùng chung trong Project này.
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => fileInput.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  Thêm
                </Button>
              </div>
              <input
                ref={fileInput}
                type="file"
                className="hidden"
                aria-label="Add project document"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadDocument(file);
                }}
              />
              <div className="mt-3 space-y-2 text-sm">
                {documents.length === 0 ? (
                  <div className="text-muted-foreground">Chưa có tài liệu Project.</div>
                ) : (
                  documents.map((document) => (
                    <div
                      key={document.document.document_id}
                      className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-2"
                    >
                      <FileText className="h-4 w-4 shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{document.document.name}</span>
                      <span className="text-xs text-muted-foreground">{document.status}</span>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Delete ${document.document.name}`}
                        onClick={() => void removeDocument(document.document.document_id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </section>
            <section className="border-t border-destructive/30 pt-5">
              <div className="text-sm font-medium text-destructive">Khu vực nguy hiểm</div>
              <p className="mt-1 text-xs text-muted-foreground">
                Xóa vĩnh viễn Project cùng mọi hội thoại và tài liệu thuộc Project này.
              </p>
              <Button
                className="mt-3 w-full"
                variant="destructive"
                onClick={() => setDeleteConfirmationOpen(true)}
              >
                <Trash2 className="h-4 w-4" /> Xóa Project
              </Button>
            </section>
          </div>
        </SheetContent>
      </Sheet>
      <Dialog open={deleteConfirmationOpen} onOpenChange={setDeleteConfirmationOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xóa Project “{project.name}”?</DialogTitle>
            <DialogDescription>
              Tất cả hội thoại và tài liệu của Project này sẽ bị xóa vĩnh viễn. Thao tác này không
              thể hoàn tác.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmationOpen(false)}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={() => void removeProject()} disabled={deleting}>
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Xóa Project
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
