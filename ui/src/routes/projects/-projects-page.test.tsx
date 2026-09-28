import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));

vi.mock("@tanstack/react-router", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({
      children,
      to,
      params,
      className,
    }: {
      children: ReactNode;
      to: string;
      params?: { projectId?: string };
      className?: string;
    }) => (
      <a href={to.replace("$projectId", params?.projectId || "")} className={className}>
        {children}
      </a>
    ),
    useNavigate: () => navigateMock,
    useRouterState: ({
      select,
    }: {
      select: (state: { location: { pathname: string } }) => unknown;
    }) => select({ location: { pathname: "/projects" } }),
  };
});

import { AppSidebar } from "@/components/AppSidebar";
import { ChatProvider } from "@/lib/chat-store";
import { invalidateProjectList } from "@/lib/project-list";
import { ProjectsPage } from "@/routes/projects/index";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
}

const alpha = {
  project_id: "project-a",
  name: "alpha",
  description: "Project description",
  instructions: "Project instructions",
  metadata: { owner: "local" },
  created_at: "now",
  updated_at: "now",
};

function renderMountedProjects() {
  return render(
    <ChatProvider>
      <AppSidebar />
      <ProjectsPage />
    </ChatProvider>,
  );
}

describe("Projects landing synchronization", () => {
  beforeEach(() => {
    window.localStorage.clear();
    navigateMock.mockReset();
    vi.restoreAllMocks();
  });

  it("updates and removes main cards after sidebar rename/delete without reload", async () => {
    let projects = [alpha];
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/sessions") return jsonResponse([]);
      if (path === "/api/projects" && !init?.method) return jsonResponse(projects);
      if (path === "/api/projects/project-a" && init?.method === "PUT") {
        projects = [{ ...alpha, ...JSON.parse(String(init.body)) }];
        return jsonResponse(projects[0]);
      }
      if (path === "/api/projects/project-a" && init?.method === "DELETE") {
        projects = [];
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderMountedProjects();

    const main = screen.getByRole("main");
    const oldCard = await within(main).findByRole("link", { name: /alpha/ });
    expect(oldCard.getAttribute("href")).toBe("/projects/project-a");
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project alpha" }));
    fireEvent.click(await screen.findByText("Đổi tên"));
    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: "beta" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await within(main).findByRole("link", { name: /beta/ });
    expect(within(main).queryByRole("link", { name: /alpha/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Quản lý Project beta" })).toBeTruthy();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Quản lý Project beta" }));
    fireEvent.click(await screen.findByText("Xóa"));
    const confirmation = await screen.findByRole("dialog", { name: "Xóa Project?" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Xóa" }));

    await waitFor(() => expect(within(main).queryByRole("link", { name: /beta/ })).toBeNull());
    expect(oldCard.isConnected).toBe(false);
    expect(screen.queryByRole("button", { name: "Quản lý Project beta" })).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("ignores an older list response after a newer explicit Project update", async () => {
    let calls = 0;
    let resolveStale: ((response: Response) => void) | undefined;
    const beta = { ...alpha, name: "beta" };
    const fetchMock = vi.fn((path: string) => {
      if (path !== "/api/projects") throw new Error(`unexpected endpoint ${path}`);
      calls += 1;
      if (calls === 2) {
        return new Promise<Response>((resolve) => {
          resolveStale = resolve;
        });
      }
      return Promise.resolve(jsonResponse(calls >= 3 ? [beta] : [alpha]));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProjectsPage />);

    const main = screen.getByRole("main");
    await within(main).findByRole("link", { name: /alpha/ });
    invalidateProjectList();
    await waitFor(() => expect(calls).toBe(2));
    invalidateProjectList({ type: "updated", project: beta });
    await within(main).findByRole("link", { name: /beta/ });
    await act(async () => {
      resolveStale?.(jsonResponse([alpha]));
    });
    expect(within(main).queryByRole("link", { name: /alpha/ })).toBeNull();
  });

  it("keeps existing card navigation and Project creation behavior", async () => {
    let projects = [alpha];
    const created = { ...alpha, project_id: "project-new", name: "new Project" };
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/projects" && !init?.method) return jsonResponse(projects);
      if (path === "/api/projects" && init?.method === "POST") {
        projects = [...projects, created];
        return jsonResponse(created);
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ProjectsPage />);

    const main = screen.getByRole("main");
    expect((await within(main).findByRole("link", { name: /alpha/ })).getAttribute("href")).toBe(
      "/projects/project-a",
    );
    fireEvent.change(screen.getByLabelText("Project name"), {
      target: { value: "new Project" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({
        to: "/projects/$projectId",
        params: { projectId: "project-new" },
      }),
    );
    await within(main).findByRole("link", { name: /new Project/ });
  });
});
