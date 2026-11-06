/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { Reasoning, ReasoningContent, ReasoningTrigger } from "./reasoning";

function setup({
  isStreaming,
  defaultOpen,
}: {
  isStreaming: boolean;
  defaultOpen?: boolean;
}) {
  return render(
    <Reasoning
      isStreaming={isStreaming}
      {...(defaultOpen !== undefined && { defaultOpen })}
    >
      <ReasoningTrigger />
      <ReasoningContent>Some reasoning content.</ReasoningContent>
    </Reasoning>,
  );
}

describe("Reasoning", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("sets no outer margin, so the message container owns the rhythm", () => {
    const { container } = setup({ isStreaming: false });
    const root = container.firstElementChild;
    if (!(root instanceof HTMLElement)) throw new Error("the block drew nothing");
    const tokens = root.className.split(/\s+/);
    expect(tokens.filter((token) => /^m[ytb]-/.test(token))).toEqual([]);
  });

  it("shows Shimmer 'Thinking...' while streaming", () => {
    setup({ isStreaming: true });
    expect(screen.getByText("Thinking...")).toBeInTheDocument();
  });

  it("reports 'Thought for N seconds' after streaming ends", async () => {
    const { rerender } = setup({ isStreaming: true });
    act(() => {
      vi.advanceTimersByTime(3500);
    });
    rerender(
      <Reasoning isStreaming={false}>
        <ReasoningTrigger />
        <ReasoningContent>Some reasoning content.</ReasoningContent>
      </Reasoning>,
    );
    expect(screen.getByText(/Thought for 4 seconds/)).toBeInTheDocument();
  });

  it("auto-closes 1s after streaming ends", async () => {
    const { rerender } = setup({ isStreaming: true });
    expect(screen.queryByText("Some reasoning content.")).toBeInTheDocument();
    rerender(
      <Reasoning isStreaming={false}>
        <ReasoningTrigger />
        <ReasoningContent>Some reasoning content.</ReasoningContent>
      </Reasoning>,
    );
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect(screen.queryByText("Some reasoning content.")).toBeNull();
  });

  it("does not auto-close if the component never streamed", () => {
    setup({ isStreaming: false, defaultOpen: true });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.queryByText("Some reasoning content.")).toBeInTheDocument();
  });

  it("shows the scrollbar of the reasoning box", () => {
    setup({ isStreaming: true });
    const box = screen.getByTestId("reasoning-scroll");
    expect(box).not.toHaveClass("no-scrollbar");
    expect(box).toHaveClass("overflow-y-auto");
  });

  it("expands the reasoning box to its full height and collapses it back", () => {
    setup({ isStreaming: false, defaultOpen: true });
    const box = screen.getByTestId("reasoning-scroll");
    const toggle = screen.getByRole("button", { name: "Show all" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", box.id);
    expect(box).toHaveClass("max-h-[12.5rem]");

    act(() => {
      toggle.click();
    });
    const collapse = screen.getByRole("button", { name: "Show less" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    expect(box).not.toHaveClass("max-h-[12.5rem]");
    expect(box).not.toHaveClass("overflow-y-auto");

    act(() => {
      collapse.click();
    });
    expect(screen.getByRole("button", { name: "Show all" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(box).toHaveClass("max-h-[12.5rem]");
  });

  it("keeps the newest reasoning in view while it streams", () => {
    const { rerender } = setup({ isStreaming: true });
    const box = screen.getByTestId("reasoning-scroll");
    Object.defineProperty(box, "scrollHeight", { configurable: true, value: 640 });
    rerender(
      <Reasoning isStreaming>
        <ReasoningTrigger />
        <ReasoningContent>Some reasoning content. And more.</ReasoningContent>
      </Reasoning>,
    );
    expect(box.scrollTop).toBe(640);
  });

  it("does not auto-open when defaultOpen={false}", () => {
    setup({ isStreaming: true, defaultOpen: false });
    expect(screen.getByText("Thinking...")).toBeInTheDocument();
    expect(screen.queryAllByText("Some reasoning content.")).toHaveLength(0);
  });
});
