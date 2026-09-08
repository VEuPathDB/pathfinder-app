/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const viewportProps: Record<string, unknown>[] = [];

vi.mock("@assistant-ui/react", () => ({
  ThreadPrimitive: {
    Viewport: ({ children, ...props }: { children?: ReactNode }) => {
      viewportProps.push(props as Record<string, unknown>);
      return <div data-testid="thread-viewport">{children}</div>;
    },
    ScrollToBottom: ({ children }: { children?: ReactNode }) => (
      <div data-testid="scroll-to-bottom">{children}</div>
    ),
  },
}));

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "./conversation";

describe("the thread's message list", () => {
  it("spaces one message from the next with the one paragraph gap", () => {
    const { container } = render(
      <ConversationContent>
        <p>a message</p>
      </ConversationContent>,
    );
    const list = container.firstElementChild;
    if (!(list instanceof HTMLElement)) throw new Error("the list drew nothing");
    const tokens = list.className.split(/\s+/);
    expect(tokens).toContain("gap-3");
    expect(tokens.filter((token) => token.startsWith("gap-"))).toEqual(["gap-3"]);
  });
});

describe("the thread scroll surface", () => {
  it("is the thread primitive's own viewport, scrolling to the bottom on send", () => {
    render(
      <>
        <Conversation>
          <ConversationContent>
            <p>a message</p>
          </ConversationContent>
        </Conversation>
        <ConversationScrollButton />
      </>,
    );

    expect(screen.getByTestId("thread-viewport")).toBeInTheDocument();
    expect(screen.getByText("a message")).toBeInTheDocument();
    expect(screen.getByTestId("scroll-to-bottom")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Scroll to the latest message" }).className,
    ).toContain("disabled:invisible");

    const props = viewportProps[viewportProps.length - 1] ?? {};
    expect(props["autoScroll"]).not.toBe(false);
    expect(props["scrollToBottomOnRunStart"]).not.toBe(false);
    expect(props["turnAnchor"]).not.toBe("top");
  });

  it("keeps its own rail, which takes no room of its own above the composer", () => {
    render(<ConversationScrollButton />);
    const rail = screen.getByTestId("conversation-scroll-rail");
    const tokens = rail.className.split(/\s+/);
    expect(tokens).toContain("relative");
    expect(tokens).toContain("h-0");
    expect(
      rail.contains(
        screen.getByRole("button", { name: "Scroll to the latest message" }),
      ),
    ).toBe(true);
  });
});
