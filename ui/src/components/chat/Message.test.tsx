import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssistantMessage } from "@/components/chat/Message";

describe("AssistantMessage", () => {
  it("keeps Copy and removes the unavailable regenerate action", () => {
    render(<AssistantMessage content="answer">answer</AssistantMessage>);

    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
  });

  it("renders provider-backed response and token metrics", () => {
    render(
      <AssistantMessage
        content="answer"
        responseTimeMs={2400}
        inputTokens={1824}
        outputTokens={216}
      >
        answer
      </AssistantMessage>,
    );

    expect(screen.getByText(/Trả lời trong 2,4 giây/)).toBeTruthy();
    expect(screen.getByText(/1.824 token vào · 216 token ra/)).toBeTruthy();
  });

  it("omits historical timing and incomplete token usage", () => {
    render(
      <AssistantMessage content="answer" inputTokens={1824}>
        answer
      </AssistantMessage>,
    );

    expect(screen.queryByText("Chưa ghi nhận thời gian")).toBeNull();
    expect(screen.queryByText(/token vào/)).toBeNull();
  });
});
