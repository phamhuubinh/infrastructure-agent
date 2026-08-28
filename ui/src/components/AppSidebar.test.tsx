import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tanstack/react-router", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
      <a {...props}>{children}</a>
    ),
    useNavigate: () => vi.fn(),
    useRouterState: ({
      select,
    }: {
      select: (state: { location: { pathname: string } }) => unknown;
    }) => select({ location: { pathname: "/projects/project-a" } }),
  };
});

import { AppSidebar, splitWorkspaceSessions } from "@/components/AppSidebar";
import { ChatProvider, type Session } from "@/lib/chat-store";
import { invalidateProjectList } from "@/lib/project-list";

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
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps Project conversations out of the ordinary Chat list", () => {
    const grouped = splitWorkspaceSessions([
      session("chat-1", null),
      session("project-a-1", "project-a"),
      session("project-b-1", "project-b"),
    ]);

    expect(grouped.chatSessions.map((item) => item.id)).toEqual(["chat-1"]);
    expect(grouped.projectSessions.map((item) => item.id)).toEqual(["project-a-1", "project-b-1"]);
  });

  it("refreshes visible Project identities after canonical Project list invalidation", async () => {
    let projectListCalls = 0;
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/sessions") return Promise.resolve(jsonResponse([]));
      if (path === "/api/projects") {
        projectListCalls += 1;
        return Promise.resolve(
          jsonResponse([
            {
              project_id: "project-a",
              name: projectListCalls === 1 ? "Atlas rollout" : "Atlas canonical rename",
              description: null,
              instructions: null,
              metadata: {},
              created_at: "now",
              updated_at: "now",
            },
          ]),
        );
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <AppSidebar />
      </ChatProvider>,
    );

    await screen.findByText("Atlas rollout");
    invalidateProjectList();
    await screen.findByText("Atlas canonical rename");
    expect(projectListCalls).toBe(2);
  });
});

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
}
