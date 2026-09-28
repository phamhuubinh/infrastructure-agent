import { deleteProject, updateProject, type Project, type ProjectInput } from "@/lib/api";
import { invalidateProjectList } from "@/lib/project-list";

export async function saveProject(projectId: string, input: ProjectInput): Promise<Project> {
  const updated = await updateProject(projectId, input);
  invalidateProjectList({ type: "updated", project: updated });
  return updated;
}

export async function removeProject(projectId: string): Promise<void> {
  await deleteProject(projectId);
  invalidateProjectList({ type: "deleted", projectId });
}
