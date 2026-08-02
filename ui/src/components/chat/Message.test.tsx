import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssistantMessage } from "@/components/chat/Message";

describe("AssistantMessage regenerate action", () => {
  it("calls the regenerate handler", () => {
    const onRegenerate = vi.fn();
    render(
      <AssistantMessage content="answer" onRegenerate={onRegenerate}>
        answer
      </AssistantMessage>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(onRegenerate).toHaveBeenCalledOnce();
  });

  it("disables regenerate while the session is generating", () => {
    const onRegenerate = vi.fn();
    render(
      <AssistantMessage content="answer" onRegenerate={onRegenerate} regenerateDisabled>
        answer
      </AssistantMessage>,
    );

    const button = screen.getByRole("button", { name: "Regenerate" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(onRegenerate).not.toHaveBeenCalled();
  });

  it("disables regenerate when onRegenerate is undefined (older message)", () => {
    render(
      <AssistantMessage content="answer" onRegenerate={undefined}>
        answer
      </AssistantMessage>,
    );

    const button = screen.getByRole("button", { name: "Regenerate" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
