import { describe, expect, it, vi } from "vitest";

import {
  apiErrorMessage,
  apiFetch,
  getAuthSession,
  login,
  logout,
  AUTH_EXPIRED_EVENT,
  attachSessionDocument,
  attachProjectDocument,
  createProject,
  deleteProject,
  deleteProjectDocument,
  deleteSessionDocument,
  sessionDocumentStatus,
} from "@/lib/api";

describe("M1 API client", () => {
  it("uses same-origin cookie login and signals an expired protected session", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response('{"remote_access":true,"authenticated":false,"expires_at":null}'),
      )
      .mockResolvedValueOnce(new Response('{"authenticated":true}'))
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      expect((await getAuthSession()).authenticated).toBe(false);
      await login("private-password");
      await apiFetch("/api/projects");
      await logout();
      expect(expired).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
        "/api/auth/session",
        "/api/auth/login",
        "/api/projects",
        "/api/auth/logout",
      ]);
      expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
      expect(fetchMock.mock.calls[1][1].body).toBe('{"password":"private-password"}');
      expect(fetchMock.mock.calls[1][1].credentials).toBeUndefined();
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    }
  });
  it("treats logout 401 as already signed out", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      await expect(logout()).resolves.toBeUndefined();
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/auth/logout",
        expect.objectContaining({ method: "POST" }),
      );
      expect(expired).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    }
  });
  it("does not retain or attach browser credentials", async () => {
    const originalFetch = globalThis.fetch;
    let captured: Headers | undefined;
    globalThis.fetch = async (_input, init) => {
      captured = new Headers(init?.headers);
      return new Response("{}", { status: 200 });
    };

    try {
      await apiFetch("/api/models");
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(captured?.has("Authorization")).toBe(false);
    expect(captured?.has("X-API-Key")).toBe(false);
  });

  it("keeps a canonical API detail message", async () => {
    const response = new Response('{"detail":"No active model configuration"}', {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
    await expect(apiErrorMessage(response)).resolves.toBe("No active model configuration");
  });

  it("redacts configured marker values from frontend activity errors", async () => {
    const response = new Response(
      '{"detail":"ORION_TEST_SECRET_TOKEN ORION_TEST_PRIVATE_URL /private/test/key"}',
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
    const message = await apiErrorMessage(response);
    expect(message).not.toContain("ORION_TEST_SECRET_TOKEN");
    expect(message).not.toContain("ORION_TEST_PRIVATE_URL");
    expect(message).not.toContain("/private/test/key");
  });

  it("uses multipart bytes on the session attachment route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            document: {
              document_id: "doc-1",
              source: { kind: "session", source_id: "session-1" },
              name: "scan.pdf",
              media_type: "application/pdf",
            },
            attachment_id: "attachment-1",
            status: "uploaded",
            error_message: null,
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(new Response('{"detail":"Document not found."}', { status: 404 }))
      .mockResolvedValueOnce(new Response('{"status":"deleted"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const bytes = new Uint8Array([0, 255, 1, 2]);

    await attachSessionDocument(
      "session-1",
      new File([bytes], "scan.pdf", { type: "application/pdf" }),
    );
    await expect(sessionDocumentStatus("session-1", "doc-1")).resolves.toBeNull();
    await deleteSessionDocument("session-1", "doc-1");

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/sessions/session-1/attachments",
      "/api/sessions/session-1/documents/doc-1",
      "/api/sessions/session-1/documents/doc-1",
    ]);
    const form = fetchMock.mock.calls[0][1]?.body as FormData;
    const uploaded = form.get("file") as File;
    expect(form).toBeInstanceOf(FormData);
    expect(uploaded.name).toBe("scan.pdf");
    expect(uploaded.type).toBe("application/pdf");
    expect(new Uint8Array(await uploaded.arrayBuffer())).toEqual(bytes);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has("Content-Type")).toBe(false);
    expect(fetchMock.mock.calls[2][1]?.method).toBe("DELETE");
  });

  it("uses Project-owned creation and multipart document routes without project_id fields", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ project_id: "project-a", name: "A" }), { status: 201 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            document: {
              document_id: "project-doc",
              source: { kind: "project", source_id: "project-a" },
              name: "requirements.txt",
              media_type: "text/plain",
            },
            attachment_id: "upload-a",
            status: "ready",
            error_message: null,
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(new Response('{"status":"deleted"}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await createProject({ name: "A", description: null, instructions: null, metadata: {} });
    await attachProjectDocument(
      "project-a",
      new File(["durable fact"], "requirements.txt", { type: "text/plain" }),
    );
    await deleteProjectDocument("project-a", "project-doc");

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/projects",
      "/api/projects/project-a/documents",
      "/api/projects/project-a/documents/project-doc",
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).not.toHaveProperty("project_id");
    const form = fetchMock.mock.calls[1][1]?.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect((form.get("file") as File).name).toBe("requirements.txt");
  });

  it("uses the canonical Project deletion route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteProject("project-a");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-a",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
