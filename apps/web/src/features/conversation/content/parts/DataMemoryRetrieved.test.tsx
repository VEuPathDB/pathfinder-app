/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { DataMemoryRetrieved } from "./DataMemoryRetrieved";

const MEMORIES = {
  memories: [
    {
      key: "m1",
      kind: "gene_set_note",
      name: "Erythrocytic genes",
      summary: "150 genes from PlasmoDB",
      score: 0.92,
    },
    {
      key: "m2",
      kind: "strategy",
      name: "Kinome sweep",
      summary: "prior strategy",
      score: 0.7,
    },
  ],
};

describe("DataMemoryRetrieved", () => {
  it("renders one row per memory with its kind badge and name", () => {
    render(<DataMemoryRetrieved data={MEMORIES} />);
    const card = screen.getByTestId("data-memory-retrieved");
    const rows = within(card).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("gene_set_note");
    expect(rows[0]).toHaveTextContent("Erythrocytic genes");
    expect(rows[1]).toHaveTextContent("strategy");
    expect(rows[1]).toHaveTextContent("Kinome sweep");
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
