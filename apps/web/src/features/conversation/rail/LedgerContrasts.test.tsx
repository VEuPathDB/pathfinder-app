// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ContrastSummary } from "@pathfinder/shared/generated/types/ContrastSummary";
import { LedgerContrasts } from "./LedgerContrasts";

afterEach(cleanup);

const contrast = (over: Partial<ContrastSummary> = {}): ContrastSummary => ({
  criterionId: "female_enrichment",
  comparator: "female",
  reference: "male",
  direction: "up-regulated",
  summary: "up-regulated in female vs male",
  ...over,
});

describe("LedgerContrasts", () => {
  it("states the contrast the way a biologist would read it", () => {
    const { container } = render(<LedgerContrasts contrasts={[contrast()]} />);
    expect(container).toHaveTextContent(
      "female_enrichment·up-regulated in female vs male",
    );
  });

  it("shows an inverted contrast differently so it can be spotted", () => {
    // The whole point: comparator/reference swapped returns a full, plausible
    // gene set of the WRONG biology. It has to look different on screen.
    render(
      <LedgerContrasts
        contrasts={[
          contrast({
            comparator: "male",
            reference: "female",
            summary: "up-regulated in male vs female",
          }),
        ]}
      />,
    );
    expect(screen.getByText("up-regulated in male vs female")).toBeVisible();
    expect(screen.queryByText("up-regulated in female vs male")).toBe(null);
  });

  it("names the criterion each contrast belongs to", () => {
    render(<LedgerContrasts contrasts={[contrast()]} />);
    expect(screen.getByText(/female_enrichment/)).toBeVisible();
  });

  it("flags a contrast that is still missing a side", () => {
    render(
      <LedgerContrasts
        contrasts={[
          contrast({ reference: null, summary: "up-regulated in female vs (unset)" }),
        ]}
      />,
    );
    expect(screen.getByText("up-regulated in female vs (unset)")).toBeVisible();
    expect(screen.getByText(/incomplete/i)).toHaveTextContent("(incomplete)");
  });

  it("paints an incomplete contrast with the warning token and no alpha", () => {
    render(
      <LedgerContrasts
        contrasts={[
          contrast({ reference: null, summary: "up-regulated in female vs (unset)" }),
        ]}
      />,
    );
    expect(screen.getByText("up-regulated in female vs (unset)")).toHaveClass(
      "text-warning",
    );
    expect(screen.getByText("(incomplete)")).toHaveClass("text-warning");
    expect(screen.getByText("(incomplete)").className).not.toContain("text-warning/");
  });

  it("renders nothing when no criterion contrasts two groups", () => {
    const { container } = render(<LedgerContrasts contrasts={[]} />);
    expect(container.textContent).toBe("");
  });

  it("lists every contrast when a strategy has several", () => {
    render(
      <LedgerContrasts
        contrasts={[
          contrast(),
          contrast({
            criterionId: "stage",
            summary: "down-regulated in larva vs adult",
          }),
        ]}
      />,
    );
    expect(screen.getByText("up-regulated in female vs male")).toBeVisible();
    expect(screen.getByText("down-regulated in larva vs adult")).toBeVisible();
  });
});
