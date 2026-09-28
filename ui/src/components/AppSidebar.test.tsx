import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { navigateMock, routerPath } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  routerPath: { value: "/projects/project-a" },
}));

vi.mock("@tanstack/react-router", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
      <a {...props}>{children}</a>
    ),
    useNavigate: () => navigateMock,
    useRouterState: ({
      select,
    }: {
      select: (state: { location: { pathname: string } }) => unknown;
    }) => select({ location: { pathname: routerPath.value } }),
  };
});

import { AppSidebar, splitWorkspaceSessions } from "@/components/AppSidebar";
import { ChatProvider, type Session } from "@/lib/chat-store";
import { invalidateProjectList } from "@/lib/project-list";
import { ProjectWorkspace } from "@/routes/projects/$projectId";

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
    navigateMock.mockReset();
    routerPath.value = "/projects/project-a";
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

  it("renames a Project from its hover/focus menu and updates the mounted header", async () => {
    let project = {
      project_id: "project-a",
      name: "alpha",
      description: "Keep this description",
      instructions: "Keep these instructions",
      metadata: { owner: "local" },
      created_at: "now",
      updated_at: "now",
    };
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/sessions") return jsonResponse([]);
      if (path === "/api/models") return jsonResponse([{ is_active: true, model_id: "test" }]);
      if (path === "/api/projects") return jsonResponse([project]);
      if (path === "/api/projects/project-a/documents") return jsonResponse([]);
      if (path === "/api/projects/project-a" && init?.method === "PUT") {
        const body = JSON.parse(String(init.body));
        expect(body).toEqual({
          name: "beta",
          description: "Keep this description",
          instructions: "Keep these instructions",
          metadata: { owner: "local" },
        });
        project = { ...project, ...body };
        return jsonResponse(project);
      }
      if (path === "/api/projects/project-a") return jsonResponse(project);
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ChatProvider>
        <AppSidebar />
        <ProjectWorkspace projectId="project-a" />
      </ChatProvider>,
    );

    await screen.findByRole("heading", { name: "alpha" });
    const management = screen.getByRole("button", { name: "Quản lý Project alpha" });
    expect(management.className).toContain("group-hover:opacity-100");
    expect(management.className).toContain("focus-visible:opacity-100");
    fireEvent.pointerDown(management);
    fireEvent.click(await screen.findByText("Đổi tên"));
    const renameDialog = await screen.findByRole("dialog", { name: "Đổi tên Project" });
    expect((within(renameDialog).getByLabelText("Project title") as HTMLInputElement).value).toBe(
      "alpha",
    );
    expect(
      (within(renameDialog).getByLabelText("Project title") as HTMLInputElement).maxLength,
    ).toBe(200);
    fireEvent.change(within(renameDialog).getByLabelText("Project title"), {
      target: { value: "beta" },
    });
    fireEvent.keyDown(within(renameDialog).getByLabelText("Project title"), { key: "Enter" });

    await screen.findByRole("heading", { name: "beta" });
    expect(screen.getByRole("button", { name: "Quản lý Project beta" })).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Chi tiết" }));
    const details = await screen.findByRole("dialog", { name: "Chi tiết Project" });
    expect((within(details).getByLabelText("Project name") as HTMLInputElement).value).toBe("beta");
  });

  it("confirms active Project deletion, removes its conversations, and navigates away", async () => {
    let deleted = false;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            session_id: "project-conversation",
            project_id: "project-a",
            title: "Nested conversation",
            created_at: "now",
            last_activity_at: "now",
          },
        ]);
      }
      if (path === "/api/projects") {
        return jsonResponse(
          deleted
            ? []
            : [
                {
                  project_id: "project-a",
                  name: "alpha",
                  description: null,
                  instructions: null,
                  metadata: {},
                  created_at: "now",
                  updated_at: "now",
                },
              ],
        );
      }
      if (path === "/api/projects/project-a" && init?.method === "DELETE") {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ChatProvider>
        <AppSidebar />
      </ChatProvider>,
    );

    await screen.findByRole("button", { name: "Quản lý Project alpha" });
    await screen.findByText("Nested conversation");
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project alpha" }));
    fireEvent.click(await screen.findByText("Xóa"));
    const confirmation = await screen.findByRole("dialog", { name: "Xóa Project?" });
    expect(within(confirmation).getByText(/hội thoại và tài liệu Project/)).toBeTruthy();
    fireEvent.click(within(confirmation).getByRole("button", { name: "Hủy" }));
    expect(deleted).toBe(false);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project alpha" }));
    fireEvent.click(await screen.findByText("Xóa"));
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "Xóa Project?" })).getByRole("button", {
        name: "Xóa",
      }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Quản lý Project alpha" })).toBeNull(),
    );
    expect(screen.queryByText("Nested conversation")).toBeNull();
    expect(navigateMock).toHaveBeenCalledWith({ to: "/projects" });
  });

  it("deletes a non-active Project without disturbing the current workspace", async () => {
    routerPath.value = "/projects/project-b";
    let projects = [
      {
        project_id: "project-a",
        name: "alpha",
        description: null,
        instructions: null,
        metadata: {},
        created_at: "now",
        updated_at: "now",
      },
      {
        project_id: "project-b",
        name: "current",
        description: null,
        instructions: null,
        metadata: {},
        created_at: "now",
        updated_at: "now",
      },
    ];
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/sessions") return jsonResponse([]);
      if (path === "/api/models") return jsonResponse([{ is_active: true, model_id: "test" }]);
      if (path === "/api/projects") return jsonResponse(projects);
      if (path === "/api/projects/project-b") return jsonResponse(projects[1]);
      if (path === "/api/projects/project-b/documents") return jsonResponse([]);
      if (path === "/api/projects/project-a" && init?.method === "DELETE") {
        projects = projects.filter((project) => project.project_id !== "project-a");
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ChatProvider>
        <AppSidebar />
        <ProjectWorkspace projectId="project-b" />
      </ChatProvider>,
    );

    await screen.findByRole("button", { name: "Quản lý Project alpha" });
    await screen.findByRole("heading", { name: "current" });
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project alpha" }));
    fireEvent.click(await screen.findByText("Xóa"));
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "Xóa Project?" })).getByRole("button", {
        name: "Xóa",
      }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Quản lý Project alpha" })).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "Quản lý Project current" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "current" })).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
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
      if (path === "/api/sessions/project-1" && init?.method === "PATCH")
        return Promise.resolve(
          jsonResponse({
            session_id: "project-1",
            project_id: "project-a",
            title: "Renamed Project conversation",
            custom_title: "Renamed Project conversation",
          }),
        );
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
    const conversationTitle = await screen.findByLabelText("Conversation title");
    expect((conversationTitle as HTMLInputElement).maxLength).toBe(120);
    fireEvent.change(conversationTitle, {
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

    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project conversation" }));
    fireEvent.click(await screen.findByText("Đổi tên"));
    expect(screen.getByRole("dialog", { name: "Đổi tên hội thoại" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Conversation title"), {
      target: { value: "Renamed Project conversation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await screen.findByText("Renamed Project conversation");
    expect(screen.getByRole("button", { name: "Quản lý Project Atlas" })).toBeTruthy();
  });
});

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
}
