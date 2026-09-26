/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { RecalledMemoriesPayload, RecalledMemory } from "@pathfinder/shared";

import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { useSessionStore } from "@/state/useSessionStore";

import { DataMemoryRetrieved } from "./DataMemoryRetrieved";

const THREAD = "e9f2a030-4c4d-4b12-8f71-32d362d0ef95";
const LONG_GOAL =
  "Find P. falciparum 3D7 genes with a signal peptide and at least 2 transmembrane domains, then keep only those with syntenic orthologs";

function memory(over: Partial<RecalledMemory>): RecalledMemory {
  return {
    key: "m1",
    kind: "case",
    name: "Erythrocytic genes",
    summary: "",
    createdAt: "2026-09-13T12:00:00Z",
    ...over,
  };
}

const MEMORIES: RecalledMemoriesPayload = {
  memories: [
    memory({ key: "m1", kind: "gene_set_note", name: "Erythrocytic genes" }),
    memory({
      key: "m2",
      kind: "strategy",
      name: "chat-e9f2a030",
      sourceConversationId: THREAD,
    }),
  ],
};

function rows(): HTMLElement[] {
  return within(screen.getByTestId("data-memory-retrieved")).getAllByRole("listitem");
}

beforeEach(() => {
  useSessionStore.setState({ selectedSite: "plasmodb" });
});

afterEach(() => {
  useMemoryFocusStore.getState().clearFocus();
});

describe("DataMemoryRetrieved", () => {
  it("draws the kind's label and the name as two elements", () => {
    render(<DataMemoryRetrieved data={MEMORIES} />);
    const [geneSet, strategy] = rows();
    expect(within(geneSet!).getByText("Gene set")).not.toBe(
      within(geneSet!).getByText("Erythrocytic genes"),
    );
    expect(within(strategy!).getByText("Strategy")).toBeInTheDocument();
    expect(within(strategy!).getByText("chat-e9f2a030")).toBeInTheDocument();
  });

  it("crops a long name with an ellipsis and shows the whole name on hover", () => {
    render(
      <DataMemoryRetrieved
        data={{ memories: [memory({ key: "c1", name: LONG_GOAL })] }}
      />,
    );
    const name = screen.getByText(LONG_GOAL);
    expect(name).toHaveClass("truncate", "min-w-0");
    expect(name).toHaveAttribute("title", LONG_GOAL);
  });

  it("links a strategy to the conversation that wrote it", () => {
    render(<DataMemoryRetrieved data={MEMORIES} />);
    expect(screen.getByRole("link", { name: "chat-e9f2a030" })).toHaveAttribute(
      "href",
      `/plasmodb/conversation/${THREAD}`,
    );
  });

  it("opens a case on its entry in the memory settings", () => {
    render(
      <DataMemoryRetrieved
        data={{ memories: [memory({ key: "case:9b73", name: "Kinase hunt" })] }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Kinase hunt" }));
    expect(useMemoryFocusStore.getState().focused).toEqual({
      key: "case:9b73",
      kind: "case",
    });
  });

  it("draws a strategy with no conversation as text", () => {
    render(
      <DataMemoryRetrieved
        data={{
          memories: [memory({ key: "s1", kind: "strategy", name: "chat-2cc3e2fd" })],
        }}
      />,
    );
    const [row] = rows();
    expect(within(row!).queryByRole("link")).not.toBeInTheDocument();
    expect(within(row!).queryByRole("button")).not.toBeInTheDocument();
    expect(row).toHaveTextContent("chat-2cc3e2fd");
  });

  it("dates two memories that share a name, and no other", () => {
    render(
      <DataMemoryRetrieved
        data={{
          memories: [
            memory({ key: "c1", name: LONG_GOAL, createdAt: "2026-09-13T12:00:00Z" }),
            memory({ key: "c2", name: LONG_GOAL, createdAt: "2026-09-16T12:00:00Z" }),
            memory({ key: "k1", kind: "knowledge", name: "Topology to orthology" }),
          ],
        }}
      />,
    );
    const [earlier, later, other] = rows();
    expect(within(earlier!).getByTestId("memory-written")).toHaveTextContent(/Sep 13/);
    expect(within(later!).getByTestId("memory-written")).toHaveTextContent(/Sep 16/);
    expect(within(other!).queryByTestId("memory-written")).not.toBeInTheDocument();
  });

  it("titles the figure and captions it with the count", () => {
    render(<DataMemoryRetrieved data={MEMORIES} />);
    expect(screen.getByText("Recalled memories").tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("figure-caption").textContent).toBe("2 memories");
  });

  it("renders nothing (returns null) when there are no memories", () => {
    const { container } = render(<DataMemoryRetrieved data={{ memories: [] }} />);
    expect(container.innerHTML).toBe("");
  });

  it("draws no divider, no card and no outer margin", () => {
    render(<DataMemoryRetrieved data={MEMORIES} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-memory-retrieved").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});

describe("DataMemoryRetrieved on a part an earlier version wrote", () => {
  // The two rows share a name, so a current part would date both of them.
  const WITHOUT_CREATED_AT = {
    memories: [
      { key: "c1", kind: "case", name: LONG_GOAL, summary: "" },
      { key: "c2", kind: "case", name: LONG_GOAL, summary: "" },
    ],
  };

  it("shows the stale-part notice and prints no date", () => {
    const { container } = render(<DataMemoryRetrieved data={WITHOUT_CREATED_AT} />);
    expect(screen.getByTestId("stale-part-notice")).toHaveTextContent(
      "Recalled memories from an earlier version of PathFinder can't be shown.",
    );
    expect(container.textContent).not.toContain("Invalid Date");
    expect(screen.queryByTestId("data-memory-retrieved")).toBeNull();
  });
});
