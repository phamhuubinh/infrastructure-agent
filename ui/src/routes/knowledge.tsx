import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, FileText, FolderPlus, Loader2, Plus, Send, Trash2, Upload } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, apiFetch, apiJson } from "@/lib/api";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/knowledge")({
  head: () => ({
    meta: [
      { title: "Phân tích tài liệu — Orion" },
      {
        name: "description",
        content: "Project-isolated document analysis.",
      },
    ],
  }),
  component: KnowledgePage,
});

type RetrievedChunk = {
  id: string;
  text: string;
  score: number;
  payload: { filename?: string; page?: number | null };
};

type Analysis = {
  id: string;
  query: string;
  answer: string;
  retrieved: RetrievedChunk[];
  created_at: string;
};

type ProjectDocument = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
};

type RagProject = {
  id: string;
  name: string;
  description: string;
  documents: ProjectDocument[];
  analyses: Analysis[];
  created_at: string;
  updated_at: string;
};

export function KnowledgePage() {
  const [projects, setProjects] = useState<RagProject[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [query, setQuery] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(
    () => projects.find((project) => project.id === selectedId),
    [projects, selectedId],
  );

  const loadProjects = useCallback(async (preferId?: string) => {
    try {
      const data = await apiJson<{ projects: RagProject[] }>("/api/rag/projects");
      setProjects(data.projects);
      setSelectedId((current) => {
        const requested = preferId || current;
        if (requested && data.projects.some((item) => item.id === requested)) {
          return requested;
        }
        const firstUserProject = data.projects.find((item) => item.id !== "default");
        return firstUserProject?.id || data.projects[0]?.id || null;
      });
      setError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể tải project RAG.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  async function createProject() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const project = await apiJson<RagProject>("/api/rag/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });
      setName("");
      setDescription("");
      await loadProjects(project.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Tạo project thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(file: File) {
    if (!selected || selected.id === "default") return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await apiFetch(`/api/rag/projects/${selected.id}/documents`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      await loadProjects(selected.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Upload thất bại.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function runAnalysis() {
    if (!selected || !query.trim()) return;
    setBusy(true);
    try {
      await apiJson(`/api/rag/projects/${selected.id}/analyses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 5 }),
      });
      setQuery("");
      await loadProjects(selected.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Phân tích thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteDocument(docId: string) {
    if (!selected) return;
    const document = selected.documents.find((item) => item.id === docId);
    if (!window.confirm(`Xóa vĩnh viễn tài liệu "${document?.filename || docId}"?`)) return;
    setBusy(true);
    try {
      await apiJson(`/api/rag/projects/${selected.id}/documents/${docId}`, {
        method: "DELETE",
      });
      await loadProjects(selected.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Xóa tài liệu thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject() {
    if (!selected || selected.id === "default") return;
    if (!window.confirm(`Xóa vĩnh viễn project "${selected.name}" và toàn bộ tài liệu?`)) return;
    setBusy(true);
    try {
      await apiJson(`/api/rag/projects/${selected.id}`, { method: "DELETE" });
      await loadProjects();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Xóa project thất bại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader
        title="Phân tích tài liệu"
        subtitle="Mỗi project có tài liệu, index và lịch sử phân tích độc lập với Chat."
      />

      <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="border-b md:border-b-0 md:border-r border-border p-3 overflow-y-auto space-y-3 max-h-72 md:max-h-none">
          <Card className="p-3 space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <FolderPlus className="h-4 w-4 text-foreground" /> Project mới
            </div>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Tên project"
              aria-label="Tên project RAG"
            />
            <Textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Mục tiêu phân tích"
              className="min-h-16"
              aria-label="Mô tả project RAG"
            />
            <Button
              size="sm"
              className="w-full"
              disabled={!name.trim() || busy}
              onClick={() => void createProject()}
            >
              <Plus className="h-4 w-4" /> Tạo project
            </Button>
          </Card>

          <div className="space-y-1">
            {loading ? (
              <Loader2 className="mx-auto my-6 h-4 w-4 animate-spin text-titanium" />
            ) : (
              projects
                .filter((project) => project.id !== "default")
                .map((project) => (
                  <button
                    key={project.id}
                    onClick={() => setSelectedId(project.id)}
                    className={cn(
                      "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                      project.id === selectedId
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-transparent hover:bg-surface-2",
                    )}
                  >
                    <div className="text-sm font-medium truncate">{project.name}</div>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      {project.documents.length} tài liệu · {project.analyses.length} lần phân tích
                    </div>
                  </button>
                ))
            )}
          </div>
        </aside>

        <main className="min-w-0 overflow-y-auto p-5">
          {error && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {!selected || selected.id === "default" ? (
            <div className="h-full grid place-items-center text-center">
              <div>
                <BookOpen className="h-12 w-12 text-muted-foreground/40 mx-auto mb-3" />
                <h2 className="text-lg font-medium">Tạo project tài liệu đầu tiên</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Dữ liệu RAG không được chia sẻ với các session Chat.
                </p>
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-5xl space-y-5">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h1 className="text-2xl font-semibold truncate">{selected.name}</h1>
                  <p className="text-sm text-muted-foreground mt-1">
                    {selected.description || "Không có mô tả."}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void deleteProject()}
                >
                  <Trash2 className="h-4 w-4" /> Xóa project
                </Button>
              </div>

              <Card className="p-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div>
                    <h2 className="font-medium">Tài liệu</h2>
                    <p className="text-xs text-muted-foreground">
                      PDF, TXT, Markdown, CSV, JSON hoặc YAML; tối đa 50 MiB.
                    </p>
                  </div>
                  <label className="inline-flex">
                    <input
                      ref={fileRef}
                      type="file"
                      className="sr-only"
                      disabled={busy}
                      accept=".pdf,.txt,.md,.markdown,.csv,.json,.yaml,.yml,.log"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void uploadDocument(file);
                      }}
                    />
                    <span className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">
                      {busy ? (
                        <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                      ) : (
                        <Upload className="h-4 w-4" />
                      )}
                      Upload
                    </span>
                  </label>
                </div>

                <div className="space-y-2">
                  {selected.documents.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                      Chưa có tài liệu trong project.
                    </div>
                  ) : (
                    selected.documents.map((document) => (
                      <div
                        key={document.id}
                        className="flex items-center gap-3 rounded-lg border border-border px-3 py-2"
                      >
                        <FileText className="h-4 w-4 shrink-0 text-foreground" />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm truncate">{document.filename}</div>
                          <div className="text-[11px] text-muted-foreground">
                            {formatBytes(document.size_bytes)} · {document.chunk_count} chunks
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Xóa ${document.filename}`}
                          disabled={busy}
                          onClick={() => void deleteDocument(document.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </Card>

              <Card className="p-4 space-y-3">
                <div>
                  <h2 className="font-medium">Yêu cầu phân tích</h2>
                  <p className="text-xs text-muted-foreground">
                    Kết quả chỉ sử dụng tài liệu thuộc project này.
                  </p>
                </div>
                <Textarea
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Ví dụ: So sánh các phương án triển khai và nêu rủi ro chính…"
                  className="min-h-24"
                  aria-label="Yêu cầu phân tích RAG"
                />
                <div className="flex justify-end">
                  <Button
                    disabled={busy || !query.trim() || selected.documents.length === 0}
                    onClick={() => void runAnalysis()}
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    Phân tích
                  </Button>
                </div>
              </Card>

              <div className="space-y-3">
                {selected.analyses.map((analysis) => (
                  <Card key={analysis.id} className="p-4">
                    <div className="text-sm font-medium mb-3">{analysis.query}</div>
                    <div className="prose prose-sm max-w-none dark:prose-invert">
                      <Markdown remarkPlugins={[remarkGfm]}>{analysis.answer}</Markdown>
                    </div>
                    {analysis.retrieved.length > 0 && (
                      <details className="mt-4">
                        <summary className="cursor-pointer text-xs text-muted-foreground">
                          {analysis.retrieved.length} nguồn được truy xuất
                        </summary>
                        <div className="mt-2 space-y-2">
                          {analysis.retrieved.map((chunk) => (
                            <div key={chunk.id} className="rounded-md bg-surface-2 p-3 text-xs">
                              <div className="font-medium mb-1">
                                {chunk.payload.filename || "Tài liệu"}
                                {chunk.payload.page ? ` · trang ${chunk.payload.page}` : ""}
                              </div>
                              <div className="text-muted-foreground line-clamp-4">{chunk.text}</div>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}
