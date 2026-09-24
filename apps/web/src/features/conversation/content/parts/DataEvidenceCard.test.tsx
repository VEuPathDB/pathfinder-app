/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { DataEvidenceCard } from "./DataEvidenceCard";
import { EVIDENCE_CARD } from "./evidenceCardFixture";

describe("DataEvidenceCard", () => {
  it("captions the control counts and the steps the site counted", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 of 3 positive controls returned, 0 of 2 negative controls returned, 1 step counted on the site.",
    );
  });

  it("lists every control id on the list the test filed it under", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.getByTestId("evidence-ids-positive-returned").textContent).toBe(
      "PF3D7_0102600, PF3D7_0709000",
    );
    expect(screen.getByTestId("evidence-ids-positive-not-returned").textContent).toBe(
      "PF3D7_1133400",
    );
    expect(screen.getByTestId("evidence-ids-negative-not-returned").textContent).toBe(
      "TGME49_205250, PF3D7_1222600",
    );
    expect(screen.queryByTestId("evidence-ids-negative-returned")).toBeNull();
  });

  it("marks a step the site now counts differently", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    const steps = screen.getByTestId("evidence-steps");
    expect(within(steps).getByText("Genes by Molecular Weight")).toBeInTheDocument();
    expect(within(steps).getByText("1,843")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-step-changed").textContent).toBe(
      "1,851 (changed on the site)",
    );
  });

  it("links the strategy and the site's enrichment on its step page", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.getByTestId("evidence-strategy-link").getAttribute("href")).toBe(
      EVIDENCE_CARD.strategyUrl,
    );
    expect(
      screen
        .getByText("Run GO, pathway or word enrichment on plasmodb.org")
        .getAttribute("href"),
    ).toBe(EVIDENCE_CARD.strategyUrl);
  });

  it("states a refused success in the ledger's own words", () => {
    render(
      <DataEvidenceCard
        data={{
          ...EVIDENCE_CARD,
          verdict: {
            supported: false,
            pendingChecks: [],
            refusedBecause:
              "this turn built nothing and no step of the strategy is in VEuPathDB",
          },
        }}
      />,
    );

    expect(screen.getByTestId("evidence-verdict").textContent).toBe(
      "Not supported: this turn built nothing and no step of the strategy is in VEuPathDB",
    );
  });

  it("shows a pending check as neither a pass nor a failure", () => {
    render(
      <DataEvidenceCard
        data={{
          ...EVIDENCE_CARD,
          verdict: {
            supported: true,
            pendingChecks: ["Febrile vs normal"],
            refusedBecause: null,
          },
        }}
      />,
    );

    expect(screen.getByTestId("evidence-verdict").textContent).toBe(
      "Supported, 1 check pending: Febrile vs normal",
    );
  });

  it("names a strategy the site does not hold instead of a failed read", () => {
    render(
      <DataEvidenceCard
        data={{
          ...EVIDENCE_CARD,
          wdkStrategyId: null,
          strategyUrl: null,
          siteRead: "not_read",
          steps: [],
        }}
      />,
    );

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 of 3 positive controls returned, 0 of 2 negative controls returned, the strategy is not on the site yet.",
    );
  });

  it("names a site that did not answer instead of showing a zero", () => {
    render(
      <DataEvidenceCard
        data={{
          ...EVIDENCE_CARD,
          siteRead: "not_answered",
          steps: EVIDENCE_CARD.steps.map((step) => ({
            ...step,
            siteCount: null,
            drifted: false,
          })),
        }}
      />,
    );

    expect(
      within(screen.getByTestId("evidence-steps")).getByText("-"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The site did not answer at the check, so no count is shown for it.",
      ),
    ).toBeInTheDocument();
  });
});
