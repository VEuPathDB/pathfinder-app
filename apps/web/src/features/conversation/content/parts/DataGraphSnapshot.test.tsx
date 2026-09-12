/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { GraphSnapshot } from "@pathfinder/shared";

import { DataGraphSnapshot } from "./DataGraphSnapshot";

type GraphNode = GraphSnapshot["nodes"][number];

const TEXT_STEP: GraphNode = {
  id: "1",
  searchName: "GenesByText",
  estimatedSize: 2000,
};
const GO_STEP: GraphNode = {
  id: "2",
  searchName: "GenesByGoTerm",
  estimatedSize: 1342,
};

const SNAPSHOT: GraphSnapshot = {
  strategyId: "s1",
  geneCount: 1342,
  detachedStepCount: 0,
  nodes: [TEXT_STEP, GO_STEP],
  edges: [],
};

describe("DataGraphSnapshot", () => {
  it("renders one caption line counting the steps and the genes", () => {
    render(<DataGraphSnapshot data={SNAPSHOT} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 steps, 1,342 genes",
    );
  });

  it("says one step in the singular", () => {
    render(<DataGraphSnapshot data={{ ...SNAPSHOT, nodes: [TEXT_STEP] }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "1 step, 1,342 genes",
    );
  });

  it("says the count is not available when none was measured", () => {
    render(
      <DataGraphSnapshot
        data={{
          ...SNAPSHOT,
          geneCount: null,
          nodes: [{ ...TEXT_STEP, estimatedSize: null }],
        }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "1 step, count not available",
    );
  });

  it("keeps a measured zero, which says the search matched nothing", () => {
    render(<DataGraphSnapshot data={{ ...SNAPSHOT, geneCount: 0 }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe("2 steps, 0 genes");
  });

  it("names the steps the strategy does not hold", () => {
    render(<DataGraphSnapshot data={{ ...SNAPSHOT, detachedStepCount: 1 }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 steps, 1,342 genes, 1 step not in the strategy",
    );
  });

  it("counts more than one detached step in the plural", () => {
    render(<DataGraphSnapshot data={{ ...SNAPSHOT, detachedStepCount: 2 }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 steps, 1,342 genes, 2 steps not in the strategy",
    );
  });

  it("names the split even when no root carries a count", () => {
    render(
      <DataGraphSnapshot
        data={{ ...SNAPSHOT, geneCount: null, detachedStepCount: 1 }}
      />,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 steps, count not available, 1 step not in the strategy",
    );
  });

  it("carries its own testid inside a figure that draws no chrome", () => {
    const { container } = render(<DataGraphSnapshot data={SNAPSHOT} />);
    const line = screen.getByTestId("data-graph-snapshot");
    const figure = screen.getByTestId("figure");
    expect(line).toHaveTextContent("2 steps, 1,342 genes");
    expect(figure.contains(line)).toBe(true);
    expect(figure.className).toBe("");
    const titles = container.querySelectorAll("figcaption");
    expect(titles).toHaveLength(1);
    expect(titles[0]).toHaveTextContent("Strategy updated");
  });
});
