import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssistantMarkdown } from "./AssistantMarkdown";

describe("assistant Markdown", () => {
  it("renders inline multiplication and display fractions without visible TeX commands", () => {
    const { container } = render(
      <AssistantMarkdown>
        {"Result: $1589 \\times 3324$\n\n$$\n\\frac{1589 \\times 3324}{72} = 73{,}358.83\n$$"}
      </AssistantMarkdown>,
    );
    expect(container.querySelectorAll(".katex").length).toBe(2);
    expect(container.querySelector(".katex-display")).toBeTruthy();
    const visibleMath = Array.from(container.querySelectorAll(".katex-html"))
      .map((node) => node.textContent)
      .join(" ");
    expect(visibleMath).toContain("×");
    expect(visibleMath).not.toMatch(/\\frac|\\times|\{,\}/);
  });

  it("keeps ordinary Markdown and code blocks intact", () => {
    const { container } = render(
      <AssistantMarkdown>
        {"**Result:** 73,358.83\n\n```text\n$literal code$\n```"}
      </AssistantMarkdown>,
    );
    expect(screen.getByText("Result:").tagName).toBe("STRONG");
    expect(container.querySelector("pre code")?.textContent).toContain("$literal code$");
    expect(container.querySelector(".katex")).toBeNull();
  });
});
