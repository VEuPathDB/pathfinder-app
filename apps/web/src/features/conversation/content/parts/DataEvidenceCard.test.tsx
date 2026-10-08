/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { DataEvidenceCard } from "./DataEvidenceCard";
import { EVIDENCE_CARD, REVIEWED_CARD } from "./evidenceCardFixture";

describe("DataEvidenceCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

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

  it("draws the facts of the check and no verdict", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const body = screen.getByTestId("evidence-card-body").textContent;
    expect([
      /Supported/.test(body),
      /Not supported/.test(body),
      /requirements met/.test(body),
    ]).toEqual([false, false, false]);
    expect(screen.getByTestId("evidence-sample-count").textContent).toBe(
      "8 of 8 sampled genes unclear",
    );
    expect(
      within(screen.getByTestId("evidence-steps")).getAllByText("116"),
    ).toHaveLength(2);
  });

  it("lists the study steps the site did not describe as pending", () => {
    render(
      <DataEvidenceCard
        data={{ ...EVIDENCE_CARD, pendingChecks: ["Febrile vs normal"] }}
      />,
    );

    expect(screen.getByTestId("evidence-pending").textContent).toBe(
      "1 check pending: Febrile vs normal",
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

  it("captions each fit word of the sampled genes", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "8 of 8 sampled genes unclear, 3 steps counted on the site.",
    );
  });

  it("lists each requirement with what answers it and how", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const rows = within(screen.getByTestId("evidence-requirements")).getAllByRole(
      "row",
    );
    expect(rows.map((row) => row.textContent)).toEqual([
      "RequirementAnswered byHow",
      'P. falciparum 3D7 genesMessage 1. Both component searches use `organism=["Plasmodium falciparum 3D7"]`.step_80bbac4f, step_e7a86f13by a parameter',
      "with a signal peptideMessage 1. `GenesWithSignalPeptide` uses `signalp_version=SignalP-6.0`.step_80bbac4fby a search",
      "at least 2 transmembrane domainsMessage 1. `GenesByTransmembraneDomains` uses `min_tm=2` and `max_tm=99`.step_e7a86f13by a parameter",
      "signal peptide and at least 2 transmembrane domainsMessage 1. The root is an `INTERSECT` of the signal-peptide and transmembrane-domain steps.step_901d23ccby the structure",
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
      "RequirementAnswered byHow",
      "orthologs in P. vivaxMessage 2step_3c1d9a02by a transform",
      "up in gametocytesMessage 2step_3c1d9a02by an analysis",
    ]);
  });

  it("says in Answered by what nothing answers and what no search states", () => {
    const review = REVIEWED_CARD.review ?? {};
    const unanswered = (text: string, status: "unmet" | "unexpressed") => ({
      text,
      turn: 1,
      answeredBy: [],
      how: "search" as const,
      status,
      note: "",
    });
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            requirements: [
              unanswered("at least 2 transmembrane domains", "unmet"),
              unanswered("exported to the host cell", "unexpressed"),
            ],
          },
        }}
      />,
    );

    expect(
      screen
        .getAllByTestId("evidence-requirement-answer")
        .map((cell) => cell.textContent),
    ).toEqual([
      "Nothing in the strategy answers it",
      "No search on this site states it",
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

  it("lists each column the check read as a row, before the sampled genes", () => {
    const review = REVIEWED_CARD.review ?? {};
    const fit = {
      criterionId: "step_e7a86f13",
      criterionText: "at least 2 transmembrane domains",
      wdkStepId: 441031663,
      column: "tm_count",
      displayName: "# TM Domains",
      boundValue: "2 to 99",
      countedIn: "genes" as const,
      total: 840,
      fitting: 840,
      fittingAtMost: 840,
      shown: true,
      fits: "all" as const,
      sentence: "840 of 840 genes fit # TM Domains (2 to 99)",
    };
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            columnFits: [
              fit,
              {
                ...fit,
                column: "molecular_weight",
                displayName: "Molecular Weight",
                boundValue: "0 to 200000",
                fitting: 708,
                fittingAtMost: 756,
                fits: "some" as const,
                sentence: "",
              },
              {
                ...fit,
                column: "signalp",
                displayName: "SignalP",
                total: 0,
                fitting: 0,
                fittingAtMost: 0,
                shown: false,
                fits: "not_shown" as const,
                sentence: "",
              },
            ],
          },
        }}
      />,
    );

    const rows = screen.getAllByTestId("evidence-column-fit");
    expect(rows.map((row) => row.textContent)).toEqual([
      "at least 2 transmembrane domains# TM Domains2 to 99840 of 840 genes",
      "at least 2 transmembrane domainsMolecular Weight0 to 200000708 to 756 of 840 genes",
      "at least 2 transmembrane domainsSignalP2 to 99The site shows no column",
    ]);
    const body = screen.getByTestId("evidence-review");
    const sections = Array.from(body.children).map((node) =>
      node.getAttribute("data-testid"),
    );
    expect(sections.slice(0, 3)).toEqual([
      "evidence-requirements",
      "evidence-column-fits",
      "evidence-sampled-genes",
    ]);
  });

  it("states a threshold the step holds on neither side with both counts", () => {
    const sentence =
      "840 of 840 genes fit # TM Domains (99 or fewer); 242 to 294 of 840 genes " +
      "hold # TM Domains 5 or more and 546 to 598 hold 5 or fewer";
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...(REVIEWED_CARD.review ?? {}),
            columnFits: [
              {
                criterionId: "step_e7a86f13",
                criterionText: "at least 2 transmembrane domains",
                wdkStepId: 441031663,
                column: "tm_count",
                displayName: "# TM Domains",
                boundValue: "5",
                countedIn: "genes" as const,
                total: 840,
                fitting: 840,
                fittingAtMost: 840,
                shown: true,
                sides: [
                  {
                    value: "5",
                    above: 242,
                    aboveAtMost: 294,
                    below: 546,
                    belowAtMost: 598,
                  },
                ],
                fits: "some" as const,
                sentence,
              },
            ],
          },
        }}
      />,
    );

    const row = screen.getByTestId("evidence-column-fit");
    expect(row).toHaveTextContent(sentence);
    expect(row.querySelector(".text-destructive")).toBeNull();
  });

  it("links each source the check read", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const sources = within(screen.getByTestId("evidence-sources"));
    expect(sources.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(
      (REVIEWED_CARD.review?.sources ?? []).map((source) => source.url),
    );
    expect(sources.getByText("VEuPathDB record `PF3D7_0101000`")).toBeInTheDocument();
  });

  it("opens each source in a new tab inside the website page", () => {
    vi.spyOn(window, "top", "get").mockReturnValue(null);
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const links = within(screen.getByTestId("evidence-sources")).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("target"))).toEqual(
      links.map(() => "_blank"),
    );
    expect(links.map((a) => a.getAttribute("rel"))).toEqual(
      links.map(() => "noreferrer"),
    );
  });

  it("shows no review section on a card without one", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    const sections = Array.from(screen.getByTestId("evidence-card-body").children);
    expect(sections.map((section) => section.getAttribute("data-testid"))).toEqual([
      "evidence-controls",
      "evidence-steps",
      "evidence-citations",
      null,
    ]);
  });
});
