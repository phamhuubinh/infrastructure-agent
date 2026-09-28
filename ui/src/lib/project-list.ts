import type { Project } from "@/lib/api";

const PROJECT_LIST_INVALIDATED = "orion:project-list-invalidated";

export type ProjectListChange =
  { type: "updated"; project: Project } | { type: "deleted"; projectId: string };

/** Notify mounted Project list surfaces that canonical Project data has changed. */
export function invalidateProjectList(change?: ProjectListChange) {
  window.dispatchEvent(new CustomEvent(PROJECT_LIST_INVALIDATED, { detail: change || null }));
}

export function onProjectListInvalidated(listener: (change: ProjectListChange | null) => void) {
  const handler = (event: Event) => {
    listener((event as CustomEvent<ProjectListChange | null>).detail || null);
  };
  window.addEventListener(PROJECT_LIST_INVALIDATED, handler);
  return () => window.removeEventListener(PROJECT_LIST_INVALIDATED, handler);
}
