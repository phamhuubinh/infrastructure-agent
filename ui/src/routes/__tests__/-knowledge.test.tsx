import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KnowledgePage } from "@/routes/knowledge";

describe("M1 knowledge placeholder", () => {
  it("does not call unimplemented RAG or Project APIs", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgePage />);

    expect(screen.getByText("Chưa khả dụng")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
