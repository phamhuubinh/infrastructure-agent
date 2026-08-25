import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getProject, type Project } from "@/lib/api";
import { ChatPage } from "@/routes/index";

export const Route = createFileRoute("/projects/$projectId")({ component: ProjectPage });

function ProjectPage() {
  const { projectId } = Route.useParams();
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    let disposed = false;
    void getProject(projectId).then((loaded) => {
      if (!disposed) setProject(loaded);
    });
    return () => {
      disposed = true;
    };
  }, [projectId]);

  return project ? (
    <ChatPage project={project} />
  ) : (
    <main className="flex-1 p-8">Loading project…</main>
  );
}
