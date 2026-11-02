import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CommandsPage } from "../commands";

afterEach(() => vi.unstubAllGlobals());
const json = (value: unknown) => new Response(JSON.stringify(value));

it("pages transient command output and cancels its owned handle without dispatching shell", async () => {
  const metadata = {
    command_id: "command",
    target_ref: "ssh:fixture",
    shell: "sh",
    state: "running",
    output_available: false,
  };
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/sessions") return json([{ session_id: "session", title: "Owned session" }]);
    if (path === "/api/sessions/session/commands") return json([metadata]);
    if (path.endsWith("/command/cancel"))
      return json({ ...metadata, state: "outcome_unknown", process_tree_terminated: false });
    if (path.startsWith("/api/sessions/session/commands/command?")) {
      const offset = new URL(path, "https://fixture").searchParams.get("stdout_offset");
      return json({
        ...metadata,
        output_available: true,
        stdout: offset === "0" ? "hello" : "world",
        stdout_offset: Number(offset),
        next_stdout_offset: Number(offset) + 5,
        next_stderr_offset: 0,
      });
    }
    throw new Error("unexpected fixture path");
  });
  vi.stubGlobal("fetch", fetcher);
  render(<CommandsPage />);
  await screen.findByRole("option", { name: "Owned session" });
  fireEvent.change(screen.getByRole("combobox", { name: "Hội thoại" }), {
    target: { value: "session" },
  });
  fireEvent.click(await screen.findByRole("button", { name: "Xem output" }));
  await screen.findByText("hello");
  fireEvent.click(screen.getByRole("button", { name: "Xem output" }));
  await screen.findByText("helloworld");
  fireEvent.click(screen.getByRole("button", { name: "Dừng command" }));
  await screen.findByText(/Chưa xác định kết quả/);
  await waitFor(() => expect(screen.queryByText("helloworld")).toBeNull());
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  expect(fetcher.mock.calls.find(([, init]) => init?.method === "POST")?.[0]).toBe(
    "/api/sessions/session/commands/command/cancel",
  );
  expect(fetcher.mock.calls.some(([path]) => path.includes("/run"))).toBe(false);
});
