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

  it("captions the control counts and no count of the steps the table lists", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 of 3 positive controls returned, 0 of 2 negative controls returned.",
    );
  });

  it("writes no caption when the card holds no count to state", () => {
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: { ...REVIEWED_CARD.review, sampledGenes: [] },
        }}
      />,
    );

    expect(screen.queryAllByTestId("figure-caption")).toHaveLength(0);
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

  it("links the site's enrichment and leaves opening the strategy to the facts", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.queryAllByRole("link", { name: "Open in PlasmoDB" })).toHaveLength(0);
    const enrichment = screen.getByTestId("evidence-enrichment-link");
    expect([enrichment.textContent, enrichment.getAttribute("href")]).toEqual([
      "Run GO, pathway or word enrichment in PlasmoDB",
      EVIDENCE_CARD.strategyUrl,
    ]);
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
      "8 of 8 sampled genes unclear.",
    );
  });

  it("lists each check with its result and what the site answered", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    const rows = within(screen.getByTestId("evidence-checks")).getAllByRole("row");
    expect(rows.map((row) => row.textContent)).toEqual([
      "CheckResultWhat the site answered",
      "the strategy on the sitePassedthe site marks 3 of 3 steps valid",
      "the strategy on the sitePassedeach combine holds a count its operator allows: INTERSECT 'Intersect' holds 116 from inputs of 479 and 840",
      "P. falciparum 3D7Passedall 116 records of step 440597243 ('Intersect') hold an organism the strategy selects: Plasmodium falciparum 3D7 (116)",
      "with a signal peptideNot checkedno check reads this requirement on the site",
    ]);
  });

  it("marks a failed check", () => {
    const review = REVIEWED_CARD.review ?? {};
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            checks: [
              {
                kind: "result_count",
                subject: "the strategy on the site",
                status: "fail",
                evidence:
                  "the result step 440597243 ('Intersect') holds no record on the site",
                requirement: "",
              },
            ],
          },
        }}
      />,
    );

    const checks = within(screen.getByTestId("evidence-checks"));
    expect(checks.getByText("Failed").className).toBe("text-destructive");
  });

  it("says the site did not answer apart from a requirement no check reads", () => {
    const review = REVIEWED_CARD.review ?? {};
    render(
      <DataEvidenceCard
        data={{
          ...REVIEWED_CARD,
          review: {
            ...review,
            checks: [
              {
                kind: "result_count",
                subject: "the strategy on the site",
                status: "unchecked",
                evidence: "the site did not answer the strategy read",
                requirement: "",
                whyUnchecked: "site_unanswered",
              },
              ...(review.checks ?? []).slice(-1),
            ],
          },
        }}
      />,
    );

    const checks = within(screen.getByTestId("evidence-checks"));
    expect([
      checks.getByTestId("evidence-site-unanswered").textContent,
      ...checks.getAllByRole("row").map((row) => row.textContent),
    ]).toEqual([
      "The site did not answer, so the strategy is not checked.",
      "CheckResultWhat the site answered",
      "the strategy on the siteNo answer from the sitethe site did not answer the strategy read",
      "with a signal peptideNot checkedno check reads this requirement on the site",
    ]);
  });

  it("states no unanswered site when every unchecked check has no check", () => {
    render(<DataEvidenceCard data={REVIEWED_CARD} />);

    expect(screen.queryAllByTestId("evidence-site-unanswered")).toHaveLength(0);
  });

  it("links the site's enrichment and leaves opening the strategy to the facts", () => {
    render(<DataEvidenceCard data={EVIDENCE_CARD} />);

    expect(screen.queryAllByRole("link", { name: "Open in PlasmoDB" })).toHaveLength(0);
    const enrichment = screen.getByTestId("evidence-enrichment-link");
    expect([enrichment.textContent, enrichment.getAttribute("href")]).toEqual([
      "Run GO, pathway or word enrichment in PlasmoDB",
      EVIDENCE_CARD.strategyUrl,
    ]);
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
      "8 of 8 sampled genes unclear.",
    );
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
      countedIn: "transcripts" as const,
      total: 840,
      fitting: 840,
      fittingAtMost: 840,
      shown: true,
      fits: "all" as const,
      sentence: "840 of 840 transcripts fit # TM Domains (2 to 99)",
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
                refusedStatus: 400,
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
      "at least 2 transmembrane domains# TM Domains2 to 99840 of 840 transcripts",
      "at least 2 transmembrane domainsMolecular Weight0 to 200000708 to 756 of 840 transcripts",
      "at least 2 transmembrane domainsSignalP2 to 99The site refused this column (HTTP 400)",
    ]);
    const body = screen.getByTestId("evidence-review");
    const sections = Array.from(body.children).map((node) =>
      node.getAttribute("data-testid"),
    );
    expect(sections.slice(0, 3)).toEqual([
      "evidence-checks",
      "evidence-column-fits",
      "evidence-sampled-genes",
    ]);
  });

  it("lists the evidence the check withheld under the review", () => {
    const sentence =
      "The review lists sampled gene `PF3D7_0102200`, and no read_gene_record " +
      "call of this turn read its record.";
    render(
      <DataEvidenceCard
        data={{
          ...EVIDENCE_CARD,
          review: { withheld: [{ kind: "sampled_gene", sentence }] },
        }}
      />,
    );

    expect(
      screen.getAllByTestId("evidence-withheld-item").map((row) => row.textContent),
    ).toEqual([sentence]);
  });

  it("states a threshold the step holds on neither side with both counts", () => {
    const sentence =
      "840 of 840 transcripts fit # TM Domains (99 or fewer); 242 to 294 of 840 transcripts " +
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
                countedIn: "transcripts" as const,
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
