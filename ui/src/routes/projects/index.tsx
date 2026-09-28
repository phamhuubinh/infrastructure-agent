import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { createProject, listProjects, type Project } from "@/lib/api";
import {
  invalidateProjectList,
  onProjectListInvalidated,
  type ProjectListChange,
} from "@/lib/project-list";

export const Route = createFileRoute("/projects/")({ component: ProjectsPage });

export function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let revision = 0;
    const refresh = (change?: ProjectListChange | null) => {
      const currentRevision = ++revision;
      if (change?.type === "updated") {
        setProjects((current) =>
          current.map((project) =>
            project.project_id === change.project.project_id ? change.project : project,
          ),
        );
      } else if (change?.type === "deleted") {
        setProjects((current) =>
          current.filter((project) => project.project_id !== change.projectId),
        );
      }
      void listProjects()
        .then((loaded) => {
          if (disposed || currentRevision !== revision) return;
          setProjects(loaded);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (disposed || currentRevision !== revision) return;
          setError(reason instanceof Error ? reason.message : "Unable to load projects.");
        })
        .finally(() => {
          if (!disposed && currentRevision === revision) setLoading(false);
        });
    };
    refresh();
    const unsubscribe = onProjectListInvalidated(refresh);
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);

  async function create() {
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const project = await createProject({
        name: name.trim(),
        description: null,
        instructions: null,
        metadata: {},
      });
      invalidateProjectList();
      await navigate({ to: "/projects/$projectId", params: { projectId: project.project_id } });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create project.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="flex-1 overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-display text-4xl">Projects</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Persistent project knowledge is available only to conversations created here.
        </p>
        <div className="mt-6 flex gap-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void create();
            }}
            placeholder="Project name"
            aria-label="Project name"
            className="h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm"
          />
          <Button onClick={() => void create()} disabled={!name.trim() || creating}>
            Create project
          </Button>
        </div>
        <div className="mt-6 space-y-2">
          {loading && <div className="text-sm text-muted-foreground">Loading projects…</div>}
          {error && (
            <div role="alert" className="text-sm text-destructive">
              {error}
            </div>
          )}
          {!loading && !error && projects.length === 0 && (
            <div className="text-sm text-muted-foreground">
              No projects yet. Create one to add project-scoped knowledge.
            </div>
          )}
          {projects.map((project) => (
            <Link
              key={project.project_id}
              to="/projects/$projectId"
              params={{ projectId: project.project_id }}
              className="block rounded-xl border border-border bg-surface-2/50 p-4 hover:bg-accent"
            >
              <div className="font-medium">{project.name}</div>
              {project.description && (
                <div className="mt-1 text-sm text-muted-foreground">{project.description}</div>
              )}
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
