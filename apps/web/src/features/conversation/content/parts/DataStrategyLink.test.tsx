/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { DataStrategyLink } from "./DataStrategyLink";

const STRATEGY = {
  strategyId: "s1",
  url: "https://plasmodb.org/plasmo/app/workspace/strategies/s1",
  title: "My Strategy",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DataStrategyLink", () => {
  it("opens the strategy in a new tab when the app is not framed", () => {
    render(<DataStrategyLink data={STRATEGY} />);
    const link = screen.getByRole("link", { name: "My Strategy" });
    expect(link).toHaveAttribute("href", STRATEGY.url);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("replaces the framing site's page when the app is framed", () => {
    vi.spyOn(window, "top", "get").mockReturnValue(null);
    render(<DataStrategyLink data={STRATEGY} />);
    const link = screen.getByRole("link", { name: "My Strategy" });
    expect(link).toHaveAttribute("href", STRATEGY.url);
    expect(link).toHaveAttribute("target", "_top");
  });

  it("renders link with title", () => {
    render(
      <DataStrategyLink
        data={{
          strategyId: "s1",
          url: "https://plasmodb.org/plasmo/app/workspace/strategies/s1",
          title: "My Strategy",
        }}
      />,
    );
    expect(screen.getByTestId("data-strategy-link")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "My Strategy" });
    expect(link).toHaveAttribute(
      "href",
      "https://plasmodb.org/plasmo/app/workspace/strategies/s1",
    );
  });

  it("titles the figure Strategy and captions it with the strategy name", () => {
    render(
      <DataStrategyLink
        data={{
          strategyId: "s1",
          url: "https://plasmodb.org/plasmo/app/workspace/strategies/s1",
          title: "My Strategy",
        }}
      />,
    );
    expect(screen.getByText("Strategy").tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("figure-caption").textContent).toBe("My Strategy");
  });

  it("names the strategy by its id when the wire carries no title", () => {
    render(
      <DataStrategyLink data={{ strategyId: "s2", url: "https://plasmodb.org/s2" }} />,
    );
    expect(screen.getByRole("link", { name: "Strategy s2" })).toHaveAttribute(
      "href",
      "https://plasmodb.org/s2",
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe("Strategy s2");
  });

  it("draws no divider, no card and no outer margin", () => {
    render(
      <DataStrategyLink
        data={{ strategyId: "s1", url: "https://plasmodb.org/s1", title: "Test" }}
      />,
    );
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-strategy-link").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });
});
