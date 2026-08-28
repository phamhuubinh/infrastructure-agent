import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("uses Trò chuyện as the sole lazy ordinary Chat action", async () => {
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/sessions" && !init?.method) {
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "chat-1",
              project_id: null,
              title: "Existing conversation",
              created_at: "now",
              last_activity_at: "now",
            },
          ]),
        );
      }
      if (path === "/api/projects") return Promise.resolve(jsonResponse([]));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <AppSidebar />
      </ChatProvider>,
    );

    await screen.findByText("Existing conversation");
    expect(screen.getAllByText("Trò chuyện")).toHaveLength(1);
    expect(screen.queryByText("Đoạn chat mới")).toBeNull();
    expect(screen.getByText("Gần đây")).toBeTruthy();
    fireEvent.click(screen.getByText("Trò chuyện"));
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) => path === "/api/sessions" && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("manages persisted ordinary and Project conversation rows through one menu", async () => {
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === "/api/sessions" && !init?.method)
        return Promise.resolve(
          jsonResponse([
            {
              session_id: "chat-1",
              project_id: null,
              title: "Ordinary conversation",
              created_at: "now",
              last_activity_at: "now",
            },
            {
              session_id: "project-1",
              project_id: "project-a",
              title: "Project conversation",
              created_at: "now",
              last_activity_at: "now",
            },
          ]),
        );
      if (path === "/api/projects")
        return Promise.resolve(
          jsonResponse([
            {
              project_id: "project-a",
              name: "Atlas",
              description: null,
              instructions: null,
              metadata: {},
              created_at: "now",
              updated_at: "now",
            },
          ]),
        );
      if (path === "/api/sessions/chat-1" && init?.method === "PATCH")
        return Promise.resolve(
          jsonResponse({ session_id: "chat-1", project_id: null, title: "Renamed" }),
        );
      if (path === "/api/sessions/chat-1" && init?.method === "DELETE")
        return Promise.resolve(new Response(null, { status: 204 }));
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ChatProvider>
        <AppSidebar />
      </ChatProvider>,
    );

    await screen.findByText("Ordinary conversation");
    expect(screen.getByRole("button", { name: "Quản lý Project conversation" })).toBeTruthy();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Ordinary conversation" }));
    await screen.findByText("Đổi tên");
    expect(screen.getByText("Xóa")).toBeTruthy();
    fireEvent.click(screen.getByText("Đổi tên"));
    fireEvent.change(await screen.findByLabelText("Conversation title"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await screen.findByText("Renamed");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/chat-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "Renamed" }) }),
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Renamed" }));
    fireEvent.click(await screen.findByText("Xóa"));
    expect(screen.getByRole("heading", { name: "Xóa hội thoại?" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/sessions/chat-1",
      expect.objectContaining({ method: "DELETE" }),
    );
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Renamed" }));
    fireEvent.click(await screen.findByText("Xóa"));
    fireEvent.click(screen.getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(screen.queryByText("Renamed")).toBeNull());
  });
});

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
}
