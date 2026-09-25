/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { DataEvidenceCard } from "./DataEvidenceCard";
import { EVIDENCE_CARD, REVIEWED_CARD } from "./evidenceCardFixture";

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

    const strategy = screen.getByRole("link", { name: "Open in PlasmoDB" });
    expect([
      strategy.getAttribute("data-testid"),
      strategy.textContent,
      strategy.getAttribute("href"),
    ]).toEqual([
      "evidence-strategy-link",
      "Open in PlasmoDB",
      EVIDENCE_CARD.strategyUrl,
    ]);
    expect(
      screen
        .getByText("Run GO, pathway or word enrichment in PlasmoDB")
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

  it("captions the requirements met and each fit word of the sampled genes", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "4 of 4 requirements met, 8 of 8 sampled genes unclear, 3 steps counted on the site.",
    );
  });

  it("lists each requirement with what answers it, how and its status", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const rows = within(screen.getByTestId("evidence-requirements")).getAllByRole(
      "row",
    );
    expect(rows.map((row) => row.textContent)).toEqual([
      "RequirementAnswered byHowStatus",
      'P. falciparum 3D7 genesMessage 1. Both component searches use `organism=["Plasmodium falciparum 3D7"]`.step_80bbac4f, step_e7a86f13by a parameterMet',
      "with a signal peptideMessage 1. `GenesWithSignalPeptide` uses `signalp_version=SignalP-6.0`.step_80bbac4fby a searchMet",
      "at least 2 transmembrane domainsMessage 1. `GenesByTransmembraneDomains` uses `min_tm=2` and `max_tm=99`.step_e7a86f13by a parameterMet",
      "signal peptide and at least 2 transmembrane domainsMessage 1. The root is an `INTERSECT` of the signal-peptide and transmembrane-domain steps.step_901d23ccby the structureMet",
    ]);
  });

  it("says how a transform or a study analysis answers a requirement", () => {
    const review = REVIEWED_CARD.review ?? {};
    const answered = (how: "transform" | "analysis", text: string) => ({
      text,
      turn: 2,
      answeredBy: ["step_3c1d9a02"],
      how,
      status: "met" as const,
      note: "",
    });
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            requirements: [
              answered("transform", "orthologs in P. vivax"),
              answered("analysis", "up in gametocytes"),
            ],
          },
        }}
      />,
    );

    const rows = within(screen.getByTestId("evidence-requirements")).getAllByRole(
      "row",
    );
    expect(rows.map((row) => row.textContent)).toEqual([
      "RequirementAnswered byHowStatus",
      "orthologs in P. vivaxMessage 2step_3c1d9a02by a transformMet",
      "up in gametocytesMessage 2step_3c1d9a02by an analysisMet",
    ]);
  });

  it("marks a requirement the strategy does not meet", () => {
    const review = REVIEWED_CARD.review ?? {};
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            requirements: [
              {
                text: "at least 2 transmembrane domains",
                turn: 1,
                answeredBy: [],
                how: "search",
                status: "unmet",
                note: "no step reads transmembrane domains",
              },
            ],
          },
        }}
      />,
    );

    const status = screen.getByTestId("evidence-requirement-status");
    expect([status.textContent, status.className]).toEqual([
      "Not met",
      "text-destructive",
    ]);
  });

  it("lists every sampled gene with its product, its fit and why", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    expect(screen.getByTestId("evidence-sample-count").textContent).toBe(
      "8 of 8 sampled genes unclear",
    );
    const genes = within(screen.getByTestId("evidence-sampled-genes"));
    expect(
      genes.getAllByTestId("evidence-gene-fit").map((cell) => cell.textContent),
    ).toEqual(Array.from({ length: 8 }, () => "Unclear"));
    expect(genes.getByText("PF3D7_0102500")).toBeInTheDocument();
    expect(genes.getByText("erythrocyte binding antigen-181")).toBeInTheDocument();
  });

  it("links each source the check read", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const sources = within(screen.getByTestId("evidence-sources"));
    expect(sources.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(
      (REVIEWED_CARD.review?.sources ?? []).map((source) => source.url),
    );
    expect(sources.getByText("VEuPathDB record `PF3D7_0101000`")).toBeInTheDocument();
  });

  it("shows no review section on a card without one", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    const sections = Array.from(screen.getByTestId("evidence-card-body").children);
    expect(sections.map((section) => section.getAttribute("data-testid"))).toEqual([
      "evidence-verdict",
      "evidence-controls",
      "evidence-steps",
      "evidence-citations",
      null,
    ]);
  });
});
