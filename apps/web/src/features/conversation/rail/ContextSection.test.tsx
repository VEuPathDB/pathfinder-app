/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ContextSection } from "./ContextSection";

type Part = UIMessage["parts"][number];

function dispatch(
  phase: string,
  state: string,
  contextTokens: number,
  contextWindow: number,
  toolCallId = `sa_${phase}`,
): Part {
  return {
    type: "data-sub-agent-call",
    data: {
      toolCallId,
      subAgent: phase,
      phase,
      state,
      modelId: "openai:gpt-5.6-luna",
      contextTokens,
      contextWindow,
    },
  };
}

function leadUsage(contextTokens: number, contextWindow: number): Part {
  return {
    type: "data-lead-usage",
    data: {
      modelId: "openai:gpt-5.6-luna",
      tokens: 5000,
      costUsd: "0.01",
      contextTokens,
      contextWindow,
    },
  };
}

describe("ContextSection", () => {
  it("renders a fill bar for a running dispatch, sized by the window", () => {
    render(
      <ContextSection parts={[dispatch("frame", "started", 210_000, 1_050_000)]} />,
    );

    expect(screen.getByText("Context")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
    expect(screen.getByText("210K / 1.1M")).toBeInTheDocument();
    expect(screen.getByTestId("context-fill-frame").style.width).toBe("20%");
  });

  it("does not render a dispatch that already finished", () => {
    render(
      <ContextSection parts={[dispatch("frame", "completed", 210_000, 1_050_000)]} />,
    );

    expect(screen.queryByText("Planning")).not.toBeInTheDocument();
    expect(screen.queryByText("Context")).not.toBeInTheDocument();
  });

  it("keeps only the latest state of one dispatch", () => {
    render(
      <ContextSection
        parts={[
          dispatch("frame", "started", 100_000, 1_050_000),
          dispatch("frame", "started", 500_000, 1_050_000),
        ]}
      />,
    );

    expect(screen.getByText("500K / 1.1M")).toBeInTheDocument();
    expect(screen.getByTestId("context-fill-frame").style.width).toBe("47.6%");
  });

  it("renders the lead's own fill beside a running sub-agent", () => {
    render(
      <ContextSection
        parts={[
          leadUsage(84_000, 1_050_000),
          dispatch("verification", "started", 42_000, 1_050_000),
        ]}
      />,
    );

    expect(screen.getByText("Assistant")).toBeInTheDocument();
    expect(screen.getByText("Checking")).toBeInTheDocument();
    expect(screen.getByTestId("context-fill-lead")).toBeInTheDocument();
    expect(screen.getByTestId("context-fill-verification")).toBeInTheDocument();
  });

  it("shows the tokens without a bar when the window is unknown", () => {
    render(<ContextSection parts={[dispatch("frame", "started", 9_000, 0)]} />);

    expect(screen.getByText("9K")).toBeInTheDocument();
    expect(screen.queryByTestId("context-fill-frame")).not.toBeInTheDocument();
  });

  it("clamps a request larger than the window and flags it", () => {
    render(
      <ContextSection parts={[dispatch("frame", "started", 2_000_000, 1_050_000)]} />,
    );

    const fill = screen.getByTestId("context-fill-frame");
    expect(fill.style.width).toBe("100%");
    expect(fill.className).toContain("bg-destructive");
  });

  it("warns before the window is full", () => {
    render(
      <ContextSection parts={[dispatch("frame", "started", 890_000, 1_050_000)]} />,
    );

    expect(screen.getByTestId("context-fill-frame").className).toContain("bg-warning");
  });

  it("renders nothing when no agent reported a context size", () => {
    const { container } = render(
      <ContextSection
        parts={[dispatch("frame", "started", 0, 1_050_000), leadUsage(0, 0)]}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
