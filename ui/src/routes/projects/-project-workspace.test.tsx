import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tanstack/react-router", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return { ...actual, useNavigate: () => vi.fn() };
});

import { ChatProvider } from "@/lib/chat-store";
import { ProjectWorkspace } from "@/routes/projects/$projectId";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(events: unknown[]): Response {
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });
}

const project = {
  project_id: "project-a",
  name: "Atlas rollout",
  description: "Hidden project description",
  instructions: "Hidden project instructions",
  metadata: {},
  created_at: "2026-08-28T00:00:00Z",
  updated_at: "2026-08-28T00:00:00Z",
};

const model = {
  model_config_id: "cfg-1",
  provider_type: "openai_compatible",
  base_url: "http://model.test/v1",
  model_id: "qwen3-32b",
  is_active: true,
};

function renderWorkspace() {
  return render(
    <ChatProvider>
      <ProjectWorkspace projectId="project-a" />
    </ChatProvider>,
  );
}

describe("Project workspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps administration in details while preserving the Project workspace and ownership APIs", async () => {
    let documents = [
      {
        document: {
          document_id: "doc-1",
          source: { kind: "project", source_id: "project-a" },
          name: "rollout.md",
          media_type: "text/markdown",
        },
        attachment_id: "attachment-1",
        status: "ready",
        error_message: null,
        ingestion: [],
      },
    ];
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([model]);
      if (path === "/api/sessions" && !init?.method) {
        return jsonResponse([
          {
            session_id: "project-session",
            project_id: "project-a",
            title: "Existing Project conversation",
            created_at: "now",
            last_activity_at: "now",
          },
          {
            session_id: "ordinary-session",
            project_id: null,
            title: "Ordinary Chat",
            created_at: "now",
            last_activity_at: "now",
          },
        ]);
      }
      if (path === "/api/sessions/project-session") {
        return jsonResponse({ session_id: "project-session", project_id: "project-a" });
      }
      if (path === "/api/sessions/project-session/timeline") {
        return jsonResponse([
          {
            item_id: "project-user-1",
            session_id: "project-session",
            created_at: "now",
            kind: "user_message",
            payload: { content: "Existing Project conversation" },
            call_id: null,
            tool_name: null,
          },
        ]);
      }
      if (path === "/api/projects/project-a") {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body)) as {
            name: string;
            description: string | null;
            instructions: string | null;
          };
          return jsonResponse({ ...project, ...body, name: "Atlas canonical rename" });
        }
        return jsonResponse(project);
      }
      if (path === "/api/projects/project-a/documents" && !init?.method) {
        return jsonResponse(documents);
      }
      if (path === "/api/projects/project-a/documents" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { name: string; content: string };
        const uploaded = {
          document: {
            document_id: "doc-2",
            source: { kind: "project", source_id: "project-a" },
            name: body.name,
            media_type: "text/plain",
          },
          attachment_id: "attachment-2",
          status: "uploaded",
          error_message: null,
        };
        documents = [...documents, { ...uploaded, ingestion: [] }];
        return jsonResponse(uploaded, 201);
      }
      if (path === "/api/projects/project-a/documents/doc-1" && init?.method === "DELETE") {
        documents = documents.filter((document) => document.document.document_id !== "doc-1");
        return jsonResponse({ status: "deleted" });
      }
      if (path === "/api/projects/project-a/sessions" && init?.method === "POST") {
        return jsonResponse({ session_id: "new-project-session", project_id: "project-a" }, 201);
      }
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    await screen.findByRole("heading", { name: "Atlas rollout" });
    await screen.findByText("Existing Project conversation");
    expect(screen.queryByLabelText("Project name")).toBeNull();
    expect(screen.queryByText("Hidden project description")).toBeNull();
    expect(screen.queryByText("Hidden project instructions")).toBeNull();
    expect(screen.queryByText("Project conversations:")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith("/api/sessions/project-session", expect.anything());

    fireEvent.click(screen.getByRole("button", { name: "Chi tiết" }));
    const details = await screen.findByRole("dialog");
    expect((within(details).getByLabelText("Project name") as HTMLInputElement).value).toBe(
      "Atlas rollout",
    );
    expect(within(details).getByText("rollout.md")).toBeTruthy();
    fireEvent.change(within(details).getByLabelText("Project name"), {
      target: { value: "Atlas rollout updated" },
    });
    fireEvent.click(within(details).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-a", expect.anything()),
    );
    fireEvent.click(within(details).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await screen.findByRole("heading", { name: "Atlas canonical rename" });
    fireEvent.click(screen.getByRole("button", { name: "Chi tiết" }));
    const reopenedDetails = await screen.findByRole("dialog");
    const file = new File(["shared facts"], "shared.md", { type: "text/markdown" });
    Object.assign(file, { text: async () => "shared facts" });
    fireEvent.change(within(reopenedDetails).getByLabelText("Add project document"), {
      target: { files: [file] },
    });
    await within(reopenedDetails).findByText("shared.md");
    fireEvent.click(within(reopenedDetails).getByRole("button", { name: "Delete rollout.md" }));
    await waitFor(() => expect(within(reopenedDetails).queryByText("rollout.md")).toBeNull());
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) => path === "/api/projects/project-a/documents" && init?.method === "POST",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) =>
          path === "/api/projects/project-a/documents/doc-1" && init?.method === "DELETE",
      ),
    ).toBe(true);

    fireEvent.click(within(reopenedDetails).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Hội thoại mới" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project-a/sessions",
      expect.anything(),
    );
    expect(screen.getByRole("heading", { name: "Orion" })).toBeTruthy();
    expect(screen.queryByText("Existing Project conversation")).toBeNull();
  });

  it("keeps a new Project conversation as a blank draft until its first message", async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([model]);
      if (path === "/api/sessions" && !init?.method) return jsonResponse([]);
      if (path === "/api/projects/project-a") return jsonResponse(project);
      if (path === "/api/projects/project-a/documents" && !init?.method) return jsonResponse([]);
      if (path === "/api/projects/project-a/sessions" && init?.method === "POST") {
        return jsonResponse({ session_id: "new-project-session", project_id: "project-a" }, 201);
      }
      if (path === "/api/sessions/new-project-session/messages/stream") return sseResponse([]);
      if (path === "/api/sessions/new-project-session") {
        return jsonResponse({ session_id: "new-project-session", project_id: "project-a" });
      }
      if (path === "/api/sessions/new-project-session/timeline") return jsonResponse([]);
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    await screen.findByRole("heading", { name: "Atlas rollout" });
    expect(screen.getByRole("heading", { name: "Orion" })).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project-a/sessions",
      expect.anything(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Hội thoại mới" }));
    expect((screen.getByRole("textbox", { name: "Chat input" }) as HTMLTextAreaElement).value).toBe(
      "",
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project-a/sessions",
      expect.anything(),
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Chat input" }), {
      target: { value: "First Project message" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([path, init]) => path === "/api/projects/project-a/sessions" && init?.method === "POST",
        ),
      ).toHaveLength(1),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/new-project-session/messages/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ content: "First Project message" }),
      }),
    );

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([path]) => path === "/api/sessions/new-project-session/messages/stream",
        ),
      ).toHaveLength(1),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Stop generating" })).toBeNull(),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Chat input" }), {
      target: { value: "Second Project message" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([path]) => path === "/api/sessions/new-project-session/messages/stream",
        ),
      ).toHaveLength(2),
    );
    expect(
      fetchMock.mock.calls.filter(
        ([path, init]) => path === "/api/projects/project-a/sessions" && init?.method === "POST",
      ),
    ).toHaveLength(1);
  });

  it("requires confirmation before deleting a Project and clears local Project work on success", async () => {
    let deleted = false;
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/models") return jsonResponse([model]);
      if (path === "/api/sessions" && !init?.method) {
        return jsonResponse([
          {
            session_id: "project-session",
            project_id: "project-a",
            title: "Existing Project conversation",
            created_at: "now",
            last_activity_at: "now",
          },
        ]);
      }
      if (path === "/api/projects/project-a" && init?.method === "DELETE") {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      if (path === "/api/projects/project-a") return jsonResponse(project);
      if (path === "/api/projects/project-a/documents") return jsonResponse([]);
      if (path === "/api/projects") return jsonResponse(deleted ? [] : [project]);
      throw new Error(`unexpected endpoint ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWorkspace();

    await screen.findByRole("heading", { name: "Atlas rollout" });
    fireEvent.click(screen.getByRole("button", { name: "Chi tiết" }));
    const details = await screen.findByRole("dialog");
    fireEvent.click(within(details).getByRole("button", { name: "Xóa Project" }));
    const confirmation = await screen.findByRole("dialog", { name: /Xóa Project/ });
    expect(within(confirmation).getByText(/hội thoại và tài liệu/)).toBeTruthy();
    fireEvent.click(within(confirmation).getByRole("button", { name: "Hủy" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project-a",
      expect.objectContaining({ method: "DELETE" }),
    );

    fireEvent.click(within(details).getByRole("button", { name: "Xóa Project" }));
    fireEvent.click((await screen.findAllByRole("button", { name: "Xóa Project" })).at(-1)!);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project-a",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    expect(await screen.findByRole("heading", { name: "Orion" })).toBeTruthy();
  });
});
