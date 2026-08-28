import { describe, expect, it } from "vitest";

import { splitWorkspaceSessions } from "@/components/AppSidebar";
import type { Session } from "@/lib/chat-store";

function session(id: string, projectId: string | null): Session {
  return {
    id,
    projectId,
    title: id,
    timeline: [],
    messages: [],
    activity: [],
    documents: [],
    sources: [],
  };
}

describe("Project workspace navigation", () => {
  it("keeps Project conversations out of the ordinary Chat list", () => {
    const grouped = splitWorkspaceSessions([
      session("chat-1", null),
      session("project-a-1", "project-a"),
      session("project-b-1", "project-b"),
    ]);

    expect(grouped.chatSessions.map((item) => item.id)).toEqual(["chat-1"]);
    expect(grouped.projectSessions.map((item) => item.id)).toEqual(["project-a-1", "project-b-1"]);
  });
});
