// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Step } from "@pathfinder/shared";
import { ZeroResultHoverCard } from "./ZeroResultHoverCard";

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    displayName: "Genes by taxon",
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: {},
    estimatedSize: 0,
    isFiltered: false,
    validation: null,
    ...overrides,
  };
}

describe("ZeroResultHoverCard", () => {
  it("renders the trigger when count is 0", () => {
    render(<ZeroResultHoverCard step={makeStep({ estimatedSize: 0 })} count={0} />);
    expect(screen.getByTestId("zero-result-trigger")).toBeTruthy();
  });

  it("paints the trigger from the warning token", () => {
    render(<ZeroResultHoverCard step={makeStep({ estimatedSize: 0 })} count={0} />);
    const trigger = screen.getByTestId("zero-result-trigger");
    expect(trigger).toHaveClass("text-warning");
    expect(trigger.className).not.toContain("amber");
  });

  it("returns null (no trigger) when count > 0", () => {
    const { container } = render(
      <ZeroResultHoverCard step={makeStep({ estimatedSize: 5 })} count={5} />,
    );
    expect(
      container.querySelectorAll('[data-testid="zero-result-trigger"]'),
    ).toHaveLength(0);
  });

  it("renders suggestion list on hover when count is 0", async () => {
    const user = userEvent.setup();
    render(<ZeroResultHoverCard step={makeStep({ estimatedSize: 0 })} count={0} />);
    const trigger = screen.getByTestId("zero-result-trigger");
    await user.hover(trigger);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 250));
    });
    const card = await screen.findByTestId("zero-result-content");
    expect(card.textContent).toContain("0 results");
    expect(card.querySelectorAll("li").length).toBeGreaterThan(0);
    expect(card).toHaveClass("border-warning/40", "text-warning");
    expect(card.className).not.toContain("amber");
  });
});
