/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { StrategyMeta } from "@pathfinder/shared";

import { DataStrategyMeta } from "./DataStrategyMeta";

const META: StrategyMeta = {
  strategyId: "s1",
  name: "Febrile kinases",
  isSaved: false,
  estimatedSize: 1342,
  recordClassName: "transcript",
};

describe("DataStrategyMeta", () => {
  it("renders one caption line naming the strategy and its size", () => {
    render(<DataStrategyMeta data={META} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Febrile kinases - 1,342 genes",
    );
  });

  it("says the strategy is saved when it is", () => {
    render(<DataStrategyMeta data={{ ...META, isSaved: true }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Febrile kinases - 1,342 genes, saved",
    );
  });

  it("says the count is not available when none was measured", () => {
    render(<DataStrategyMeta data={{ ...META, estimatedSize: null }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Febrile kinases - count not available",
    );
  });

  it("keeps a measured zero, which says the search matched nothing", () => {
    render(<DataStrategyMeta data={{ ...META, estimatedSize: 0 }} />);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "Febrile kinases - 0 genes",
    );
  });

  it("carries its own testid and no title, because it has no body", () => {
    const { container } = render(<DataStrategyMeta data={META} />);
    expect(screen.getByTestId("data-strategy-meta")).toHaveTextContent(
      "Febrile kinases - 1,342 genes",
    );
    expect(container.querySelectorAll("figcaption")).toHaveLength(0);
  });

  it("stops being a bordered pill", () => {
    render(<DataStrategyMeta data={META} />);
    expect(screen.getByTestId("figure").className).toBe("");
    expect(
      screen.getByTestId("figure").contains(screen.getByTestId("data-strategy-meta")),
    ).toBe(true);
  });
});
