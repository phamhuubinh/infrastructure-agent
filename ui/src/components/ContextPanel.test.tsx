import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ContextPanel } from "@/components/ContextPanel";
import type { Session } from "@/lib/chat-store";

const session: Session = {
  id: "session-1",
  projectId: "project-a",
  title: "Project conversation",
  timeline: [],
  messages: [],
  activity: [],
  documents: [],
  sources: [],
};

describe("ContextPanel", () => {
  beforeEach(() => window.localStorage.clear());

  it("uses a layout-owned rail for its collapsed reopen control", async () => {
    window.localStorage.setItem("orion-context-panel-collapsed", "true");
    render(
      <ContextPanel session={session} selectedSourceRefId={null} onOpenSource={() => undefined} />,
    );

    const reopen = await screen.findByRole("button", { name: "Mở bảng chi tiết" });
    expect(reopen.className).not.toContain("fixed");
    expect(reopen.className).not.toContain("top-3");
    expect(screen.getByTestId("collapsed-context-panel").className).toContain("w-12");
  });

  it("renders one final card per call ID and hides started-only activity", () => {
    render(
      <ContextPanel
        session={{
          ...session,
          activity: [
            { callId: "started", toolName: "linux.system.inspect", status: "started" },
            { callId: "complete", toolName: "linux.system.inspect", status: "completed" },
            { callId: "failed", toolName: "linux.system.inspect", status: "failed" },
          ],
        }}
        selectedSourceRefId={null}
        onOpenSource={() => undefined}
      />,
    );

    expect(screen.getAllByText("linux.system.inspect")).toHaveLength(2);
    expect(screen.getByText("Hoàn tất")).toBeTruthy();
    expect(screen.getByText("Lỗi")).toBeTruthy();
    expect(screen.queryByText("Đang chạy")).toBeNull();
  });
});
