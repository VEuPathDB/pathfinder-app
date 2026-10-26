/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import type { ThreadMessageLike } from "@assistant-ui/react";
import type { UIMessage } from "ai";

import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { AssistantMessage, UserMessage } from "../content/MessageRenderer";
import { EVIDENCE_CARD } from "../content/parts/evidenceCardFixture";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() },
  Toaster: () => null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/conversation/conv-1",
}));

type Content = Exclude<ThreadMessageLike["content"], string>;

const FACTS = {
  type: "data-facts" as const,
  data: {
    recordNoun: "gene",
    steps: [],
    rootCount: 288,
    caveats: [
      { kind: "release", sentence: "The prediction uses the site's SignalP release." },
    ],
    gaps: [{ kind: "unread", sentence: "No control set was attached." }],
  },
};
const MEMORY = {
  type: "data-memory-retrieved" as const,
  data: {
    memories: [
      {
        key: "k1",
        kind: "preference",
        name: "default organism",
        summary: "",
        createdAt: "2026-09-13T12:00:00Z",
      },
    ],
  },
};
const SOURCES = {
  type: "data-research.sources" as const,
  data: {
    query: "signal peptide malaria",
    sources: [{ id: "s1", url: "https://example.org/a", title: "A paper" }],
  },
};
const EVIDENCE = { type: "data-evidence-card" as const, data: EVIDENCE_CARD };
const REPLY = { type: "text" as const, text: "The strategy is built." };

function link(title: string) {
  return {
    type: "data-strategy-link" as const,
    data: { strategyId: title, url: `https://qa.plasmodb.org/${title}`, title },
  };
}

function Thread({
  content,
  chatMessages = [],
}: {
  content: Content;
  chatMessages?: UIMessage[];
}) {
  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages: [{ role: "assistant", content }],
    convertMessage: (message) => message,
    onNew: async () => undefined,
  });
  const chat = { messages: chatMessages, status: "ready" } as unknown as ChatHelpers;
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatHelpersProvider value={chat}>
        <ThreadPrimitive.Messages components={{ AssistantMessage, UserMessage }} />
      </ChatHelpersProvider>
    </AssistantRuntimeProvider>
  );
}

function headings(): string[] {
  fireEvent.click(screen.getByTestId("turn-appendix-toggle"));
  return within(screen.getByTestId("turn-appendix"))
    .getAllByRole("heading", { level: 3 })
    .map((heading) => heading.textContent);
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("TurnAppendix", () => {
  it("draws nothing for a reply that carries no appendix part", () => {
    render(<Thread content={[REPLY]} />);

    expect(screen.queryAllByTestId("turn-appendix")).toHaveLength(0);
  });

  it("draws the turn's records below the reply instead of beside it", () => {
    render(<Thread content={[MEMORY, FACTS, REPLY]} />);

    const appendix = screen.getByTestId("turn-appendix");
    const reply = screen.getByText("The strategy is built.");
    expect(reply.compareDocumentPosition(appendix)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(within(appendix).getByTestId("data-facts")).toBeInTheDocument();
    expect(within(appendix).getByTestId("data-memory-retrieved")).toBeInTheDocument();
  });

  it("starts closed and opens from its toggle", () => {
    render(<Thread content={[FACTS, REPLY]} />);

    const toggle = screen.getByTestId("turn-appendix-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("names the result and the caveats on its closed line", () => {
    render(<Thread content={[FACTS, MEMORY, REPLY]} />);

    expect(screen.getByTestId("turn-appendix-summary")).toHaveTextContent(
      "Appendix · 2 sections · 288 genes · 2 caveats",
    );
  });

  it("names the last result when the message holds several", () => {
    const later = {
      type: "data-facts" as const,
      data: { recordNoun: "gene", steps: [], rootCount: 2 },
    };
    render(<Thread content={[FACTS, REPLY, later]} />);

    expect(screen.getByTestId("turn-appendix-summary")).toHaveTextContent(
      "Appendix · 2 sections · 2 genes",
    );
  });

  it("letters its sections in one fixed order, whatever order they arrived in", () => {
    render(<Thread content={[MEMORY, SOURCES, EVIDENCE, FACTS, REPLY]} />);

    expect(headings()).toEqual([
      "A. Strategy",
      "B. Evidence",
      "C. Sources",
      "D. Recalled memories",
    ]);
  });

  it("draws no section for the strategy's graph snapshot", () => {
    const snapshot = {
      type: "data-graph-snapshot" as const,
      data: {
        strategyId: "s1",
        geneCount: 797,
        detachedStepCount: 0,
        nodes: [{ id: "1", searchName: "GroupsByPhyleticPattern", estimatedSize: 797 }],
        edges: [],
      },
    };
    render(<Thread content={[snapshot, FACTS, REPLY]} />);

    expect(headings()).toEqual(["A. Strategy"]);
    expect(screen.getByTestId("turn-appendix")).not.toHaveTextContent(
      "Strategy updated",
    );
    expect(screen.queryAllByTestId("data-graph-snapshot")).toHaveLength(0);
  });

  it("keeps only the last of a part that restates the strategy's state", () => {
    render(<Thread content={[link("first"), link("second"), REPLY]} />);

    const appendix = screen.getByTestId("turn-appendix");
    expect(within(appendix).getAllByTestId("data-strategy-link")).toHaveLength(1);
    expect(appendix).toHaveTextContent("second");
  });

  it("reads as one column with fewer than three sections and two from three", () => {
    const { unmount } = render(<Thread content={[FACTS, MEMORY, REPLY]} />);
    expect(screen.getByTestId("turn-appendix-body")).toHaveAttribute(
      "data-columns",
      "1",
    );
    unmount();

    render(<Thread content={[FACTS, MEMORY, SOURCES, REPLY]} />);
    expect(screen.getByTestId("turn-appendix-body")).toHaveAttribute(
      "data-columns",
      "2",
    );
  });

  it("gives every section the same heading and body", () => {
    render(<Thread content={[FACTS, MEMORY, SOURCES, REPLY]} />);

    const sections = within(screen.getByTestId("turn-appendix-body")).getAllByTestId(
      "appendix-section",
    );
    expect(sections).toHaveLength(3);
    for (const section of sections) {
      expect(section.querySelector("h3")?.className).toBe(
        sections[0]?.querySelector("h3")?.className,
      );
    }
  });

  it("keeps a refusal in the reply, where it cannot be folded away", () => {
    const refused = {
      type: "data-facts" as const,
      data: { ...FACTS.data, refusal: "The site refused the edit." },
    };
    render(<Thread content={[refused, REPLY]} />);

    const notice = screen.getByTestId("facts-notice");
    expect(notice).toHaveTextContent("The site refused the edit.");
    expect(screen.getByTestId("turn-appendix").contains(notice)).toBe(false);
  });

  it("opens when a link names a table it holds", () => {
    const results = { taskId: "t1", toolCallId: "call-1" };
    const part = { type: "data-control-test-results" as const, data: results };
    const chatMessages = [
      { id: "m1", role: "assistant", parts: [part] },
    ] as unknown as UIMessage[];
    render(<Thread content={[part, REPLY]} chatMessages={chatMessages} />);

    const toggle = screen.getByTestId("turn-appendix-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    act(() => {
      window.history.replaceState(null, "", "#table-1");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
