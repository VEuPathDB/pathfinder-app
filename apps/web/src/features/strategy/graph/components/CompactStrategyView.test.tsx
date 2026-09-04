// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Strategy } from "@pathfinder/shared";

vi.mock("@/state/strategy/useStepSnapshot", () => ({
  useStepSnapshot: () => ({
    step: null,
    lifecycleState: "idle",
    estimatedSize: 42,
    validationErrors: null,
    lastError: null,
    isBusy: false,
    isInvalid: false,
    isFailed: false,
  }),
}));

import { CompactStrategyView } from "./CompactStrategyView";

const SIMPLE_STRATEGY: Strategy = {
  id: "s1",
  name: "Simple",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_a",
      kind: "search",
      displayName: "Genes by taxon",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
  ],
  rootStepId: "step_a",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

const COMBINE_STRATEGY: Strategy = {
  id: "s2",
  name: "Combine",
  siteId: "plasmodb",
  recordType: "gene",
  steps: [
    {
      id: "step_a",
      kind: "search",
      displayName: "Search A",
      searchName: "GenesByTaxon",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
    {
      id: "step_b",
      kind: "search",
      displayName: "Search B",
      searchName: "GenesByGoTerm",
      recordType: "gene",
      parameters: {},
      isFiltered: false,
    },
    {
      id: "step_c",
      kind: "combine",
      // combines arrive with the internal "__combine__" sentinel (backend
      // falls back displayName -> searchName) — must never reach the UI.
      displayName: "__combine__",
      searchName: "__combine__",
      recordType: "gene",
      parameters: {},
      operator: "INTERSECT",
      primaryInputStepId: "step_a",
      secondaryInputStepId: "step_b",
      isFiltered: false,
    },
  ],
  rootStepId: "step_c",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

describe("CompactStrategyView (vertical layout)", () => {
  afterEach(() => cleanup());

  it("renders nothing when strategy is null", () => {
    const { container } = render(<CompactStrategyView strategy={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a vertical step list for a single search", () => {
    render(<CompactStrategyView strategy={SIMPLE_STRATEGY} />);
    const list = screen.getByTestId("compact-strategy-view");
    expect(list.tagName).toBe("OL");
    expect(screen.getByText("Genes by taxon")).toBeTruthy();
  });

  it("names the operation on the combine row", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    const row = screen.getByTestId("compact-step-row-step_c");
    expect(row).toHaveTextContent("Intersect");
    expect(row).toHaveTextContent("42");
  });

  it("keeps the full expression on the combine row for hover", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    const row = screen.getByTestId("compact-step-row-step_c");
    expect(within(row).getByTitle("Search A ∩ Search B")).toBeVisible();
  });

  it("gives a combine and a leaf the same glyph column width", () => {
    // The label must start at the same x on every row, or the indentation
    // stops reading as hierarchy.
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    const glyphWidth = (id: string) =>
      screen.getByTestId(`compact-step-row-${id}`).querySelector("[aria-hidden]")
        ?.className;

    expect(glyphWidth("step_c")).toBe(glyphWidth("step_a"));
    expect(glyphWidth("step_c")).toContain("w-4");
  });

  it("left-aligns the glyph in its column", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    const glyph = screen
      .getByTestId("compact-step-row-step_c")
      .querySelector("[aria-hidden]");

    expect(glyph?.className).toContain("justify-start");
  });

  it("lists both inputs beneath the combine", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    const children = screen.getByTestId("compact-children-step_c");
    expect(children).toHaveTextContent("Search A");
    expect(children).toHaveTextContent("Search B");
  });

  it("does not label a combine with placeholder operands", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    expect(screen.queryByText(/Combine \(A ∩ B\)/i)).toBe(null);
  });

  it("never surfaces the internal __combine__ sentinel", () => {
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} />);
    expect(screen.queryByText("__combine__")).toBe(null);
  });

  it("clicking the combine result row fires onStepClick with its id", () => {
    const onClick = vi.fn();
    render(<CompactStrategyView strategy={COMBINE_STRATEGY} onStepClick={onClick} />);
    fireEvent.click(screen.getByTestId("compact-step-row-step_c"));
    expect(onClick).toHaveBeenCalledWith("step_c");
  });

  it("clicking a row fires onStepClick with the step id", () => {
    const onClick = vi.fn();
    render(<CompactStrategyView strategy={SIMPLE_STRATEGY} onStepClick={onClick} />);
    fireEvent.click(screen.getByTestId("compact-step-row-step_a"));
    expect(onClick).toHaveBeenCalledWith("step_a");
  });
});

describe("a strategy whose branches are themselves combines", () => {
  // (A u B) n (C u D): the root's second input is a combine, so a layout that
  // draws it as one row hides C and D entirely.
  const search = (id: string, displayName: string) => ({
    id,
    kind: "search" as const,
    displayName,
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: {},
    isFiltered: false,
  });
  const combine = (
    id: string,
    operator: string,
    primaryInputStepId: string,
    secondaryInputStepId: string,
  ) => ({
    id,
    kind: "combine" as const,
    displayName: "__combine__",
    searchName: "__combine__",
    recordType: "gene",
    parameters: {},
    operator,
    primaryInputStepId,
    secondaryInputStepId,
    isFiltered: false,
  });

  const NESTED: Strategy = {
    id: "s3",
    name: "Nested",
    siteId: "plasmodb",
    recordType: "gene",
    steps: [
      search("step_a", "A"),
      search("step_b", "B"),
      search("step_c", "C"),
      search("step_d", "D"),
      combine("step_ab", "UNION", "step_a", "step_b"),
      combine("step_cd", "UNION", "step_c", "step_d"),
      combine("step_root", "INTERSECT", "step_ab", "step_cd"),
    ],
    rootStepId: "step_root",
    isSaved: false,
  } as Strategy;

  // An li inside an li with no list between is invalid HTML and makes React
  // fail hydration. jsdom accepts it, so only an explicit query catches it.
  // A child ol is the legitimate way to nest, so the selector is a direct one.
  it("puts no list item directly inside another list item", () => {
    const { container } = render(<CompactStrategyView strategy={NESTED} />);

    expect(container.querySelectorAll("li > li")).toHaveLength(0);
  });

  it("separates a nested list from its parent item with an ol", () => {
    const { container } = render(<CompactStrategyView strategy={NESTED} />);

    for (const item of container.querySelectorAll("li li")) {
      expect(item.parentElement?.tagName).toBe("OL");
    }
  });

  it("makes every child of a list an li", () => {
    const { container } = render(<CompactStrategyView strategy={NESTED} />);

    for (const list of container.querySelectorAll("ol")) {
      for (const child of list.children) {
        expect(child.tagName).toBe("LI");
      }
    }
  });

  it("gives each step exactly one list item", () => {
    const { container } = render(<CompactStrategyView strategy={NESTED} />);

    expect(container.querySelectorAll("li")).toHaveLength(7);
  });

  it("shows every step, including both sides of the nested branch", () => {
    render(<CompactStrategyView strategy={NESTED} />);

    expect(
      screen.getAllByTestId(/^compact-step-row-/).map((r) => r.dataset["testid"]),
    ).toEqual([
      "compact-step-row-step_root",
      "compact-step-row-step_ab",
      "compact-step-row-step_a",
      "compact-step-row-step_b",
      "compact-step-row-step_cd",
      "compact-step-row-step_c",
      "compact-step-row-step_d",
    ]);
  });

  it("indents both inputs of a combine beneath it", () => {
    render(<CompactStrategyView strategy={NESTED} />);
    const children = screen.getByTestId("compact-children-step_root");
    expect(within(children).getByTestId("compact-step-row-step_ab")).toBeVisible();
    expect(within(children).getByTestId("compact-step-row-step_cd")).toBeVisible();
  });

  it("nests a branch's own inputs one level deeper", () => {
    render(<CompactStrategyView strategy={NESTED} />);
    const children = screen.getByTestId("compact-children-step_cd");
    expect(within(children).getByTestId("compact-step-row-step_c")).toBeVisible();
    expect(within(children).getByTestId("compact-step-row-step_d")).toBeVisible();
  });

  it("puts the root first, before anything it contains", () => {
    render(<CompactStrategyView strategy={NESTED} />);
    const rows = screen.getAllByTestId(/^compact-step-row-/);
    expect(rows[0]?.getAttribute("data-testid")).toBe("compact-step-row-step_root");
  });

  it("keeps each combine's expression available on hover", () => {
    render(<CompactStrategyView strategy={NESTED} />);
    expect(screen.getByTitle("A ∪ B")).toBeVisible();
    expect(screen.getByTitle("C ∪ D")).toBeVisible();
    expect(screen.getByTitle("(A ∪ B) ∩ (C ∪ D)")).toBeVisible();
  });

  it("renders no step twice", () => {
    render(<CompactStrategyView strategy={NESTED} />);
    expect(screen.getAllByTestId(/^compact-step-row-/)).toHaveLength(7);
  });
});
