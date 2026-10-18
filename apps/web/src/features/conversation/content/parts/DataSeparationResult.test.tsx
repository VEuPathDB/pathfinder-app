/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { SeparationReport } from "@pathfinder/shared";

import { qaRecording } from "@/lib/testing/qaRecording";
import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataSeparationResult } from "./DataSeparationResult";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

/** The recorded exact run on the seed "PF3D7 Signal Peptide Genes". */
const recorded = qaRecording(
  import.meta.url,
  "../../__fixtures__/separationResult.json",
);
const REPORT = (recorded ?? {}) as SeparationReport;

function renderReport(data: SeparationReport) {
  const messages = threadOf([threadPart("data-separation-result", data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>
      <DataSeparationResult data={data} />
    </ChatHelpersProvider>,
  );
}

function cell(name: string): HTMLElement {
  return screen.getByTestId(`separation-cell-${name}`);
}

describe.skipIf(recorded === null)("DataSeparationResult", () => {
  it("draws the four cells the site read, each with its ids", () => {
    renderReport(REPORT);

    expect(
      ["recovered", "missed", "admitted", "excluded"].map(
        (name) => within(cell(name)).getByTestId("separation-count").textContent,
      ),
    ).toEqual(["50", "30", "0", "40"]);
    expect(within(cell("admitted")).getByTestId("separation-ids").textContent).toBe("");
    expect(
      within(cell("excluded")).getByTestId("separation-ids").textContent.split(", "),
    ).toHaveLength(40);
  });

  it("says what each criterion adds and what its own step returned", () => {
    renderReport(REPORT);

    const rows = within(screen.getByTestId("separation-criteria"))
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.textContent);
    expect(rows).toEqual([
      "GO Term: GO:0044217 other organism partrecovers 42 of 80 positives, admits 0 of 40 negativeswithout it: -5 positives, 0 negatives",
      "GO Term: GO:0051701 biological process involved in interaction with hostrecovers 38 of 80 positives, admits 0 of 40 negativeswithout it: -6 positives, 0 negatives",
      "Gene Lists from Pexel motif analysis of protein export to the erythrocyte membrane.recovers 33 of 80 positives, admits 0 of 40 negativeswithout it: -2 positives, 0 negatives",
    ]);
  });

  it("draws the tree in the strategy's own words", () => {
    renderReport(REPORT);

    expect(screen.getByTestId("separation-tree").textContent).toBe(
      "UnionUnionGO Term: GO:0044217 other organism partGO Term: GO:0051701 " +
        "biological process involved in interaction with hostGene Lists from " +
        "Pexel motif analysis of protein export to the erythrocyte membrane.",
    );
  });

  it("counts the informative searches, the skipped ones and the requests", () => {
    renderReport(REPORT);

    expect(screen.getByTestId("separation-informative").textContent).toBe(
      "14 of 23 measured searches tell the positives from the negatives",
    );
    expect(screen.getByTestId("separation-requests").textContent).toBe(
      "379 of 400 requests",
    );
    expect(
      screen.getAllByTestId("separation-skipped").map((row) => row.textContent),
    ).toEqual([
      "over the request budget: 2",
      "needs a value only you can set: 4",
      "refused by the site: 2",
      "informs neither: 9",
    ]);
  });

  it("states the shortfall and captions the counts", () => {
    renderReport(REPORT);

    expect(
      screen.getAllByTestId("separation-shortfall").map((line) => line.textContent),
    ).toEqual(REPORT.shortfall);
    expect(REPORT.shortfall?.[0]).toMatch(
      /^No measured criterion recovers PF3D7_0104500, PF3D7_0105400, /,
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "no strategy separates the sets; closest: 50 of 80 positives, 0 of 40 " +
        "negatives, 800 genes, 3 searches; 379 of 400 requests",
    );
  });

  it("heads the plan's column as searches", () => {
    renderReport(REPORT);

    const heads = within(screen.getByTestId("separation-criteria"))
      .getAllByRole("columnheader")
      .map((head) => head.textContent);
    expect(heads).toEqual(["Search", "Its own step", "Ablation"]);
  });

  it("says how many measured searches the table leaves out", () => {
    renderReport(REPORT);

    expect(
      within(screen.getByTestId("separation-measured")).getAllByRole("row"),
    ).toHaveLength(11);
    expect(screen.getByTestId("separation-measured-more").textContent).toBe(
      "13 more measured searches are not shown.",
    );
  });

  it("names the controls the site does not know", () => {
    renderReport({
      ...REPORT,
      unresolvedPositive: ["PF3D7_9999900", "PF3D7_9999901"],
      unresolvedNegative: [],
    });

    expect(
      screen.getAllByTestId("separation-unresolved").map((line) => line.textContent),
    ).toEqual(["2 positives the site does not know: PF3D7_9999900, PF3D7_9999901"]);
  });

  it("says when the site's read departs from the measured sets", () => {
    const offer = REPORT.offer;
    if (offer == null) throw new Error("the recorded run offers a strategy");
    renderReport({ ...REPORT, offer: { ...offer, predictedMatchesRead: false } });

    expect(screen.getByTestId("separation-predicted").textContent).toBe(
      "The site's read of the tree differs from what the measured searches predicted.",
    );
  });

  it("says nothing of the prediction when the read matches it", () => {
    renderReport(REPORT);

    expect([
      ...screen.queryAllByTestId("separation-predicted"),
      ...screen.queryAllByTestId("separation-unresolved"),
    ]).toHaveLength(0);
  });

  it("says a run that assembled nothing offers nothing", () => {
    renderReport({
      ...REPORT,
      offer: null,
      shortfall: ["No measured criterion recovers any positive."],
    });

    expect(screen.queryByTestId("separation-cell-recovered")).toBeNull();
    expect(screen.getByTestId("separation-shortfall").textContent).toBe(
      "No measured criterion recovers any positive.",
    );
  });
});
