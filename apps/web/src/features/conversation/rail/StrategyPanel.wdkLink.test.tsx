// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Strategy } from "@pathfinder/shared";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/plasmodb/conversation/c1",
}));

import { StrategyPanel } from "./StrategyPanel";

const WDK_URL = "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/330528343";

function strategy(overrides: Partial<Strategy> = {}): Strategy {
  return {
    id: "c1",
    name: "S",
    siteId: "plasmodb",
    recordType: "gene",
    rootStepId: "step_a",
    isSaved: false,
    steps: [
      {
        id: "step_a",
        kind: "search",
        displayName: "Genes by taxon",
        searchName: "GenesByTaxon",
        recordType: "gene",
        parameters: {},
        isFiltered: false,
        estimatedSize: 132,
      },
    ],
    wdkStrategyId: 330528343,
    wdkUrl: WDK_URL,
    ...overrides,
  } as Strategy;
}

describe("the rail panel links to the host site", () => {
  afterEach(cleanup);

  // The panel is where a researcher looks first. Reaching WDK should not
  // require opening the full editor.
  it("offers a link to the strategy on the host site", () => {
    render(
      <StrategyPanel strategy={strategy()} siteId="plasmodb" conversationId="conv-1" />,
    );

    expect(screen.getByTestId("rail-strategy-wdk-link").getAttribute("href")).toBe(
      WDK_URL,
    );
  });

  it("names the site the strategy belongs to", () => {
    render(
      <StrategyPanel strategy={strategy()} siteId="plasmodb" conversationId="conv-1" />,
    );

    expect(screen.getByTestId("rail-strategy-wdk-link").textContent).toContain(
      "PlasmoDB",
    );
  });

  it("opens in a new tab without leaking the referrer", () => {
    render(
      <StrategyPanel strategy={strategy()} siteId="plasmodb" conversationId="conv-1" />,
    );
    const link = screen.getByTestId("rail-strategy-wdk-link");

    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("keeps the button that opens the full editor", () => {
    render(
      <StrategyPanel strategy={strategy()} siteId="plasmodb" conversationId="conv-1" />,
    );

    expect(screen.getByTestId("rail-strategy-open")).toBeVisible();
  });

  it("offers no link before the strategy reaches WDK", () => {
    render(
      <StrategyPanel
        strategy={strategy({ wdkUrl: null, wdkStrategyId: null })}
        siteId="plasmodb"
        conversationId="conv-1"
      />,
    );

    expect(screen.queryByTestId("rail-strategy-wdk-link")).toBe(null);
  });

  it("offers no link when there is no strategy", () => {
    render(<StrategyPanel strategy={null} siteId="plasmodb" conversationId="conv-1" />);

    expect(screen.queryByTestId("rail-strategy-wdk-link")).toBe(null);
  });
});
