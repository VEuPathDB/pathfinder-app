/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { SeparationReport } from "@pathfinder/shared";

import recorded from "../../__fixtures__/separationResult.json";
import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataSeparationResult } from "./DataSeparationResult";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

/** The recorded exact run on the seed "PF3D7 Signal Peptide Genes". */
const REPORT = recorded as SeparationReport;

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

describe("DataSeparationResult", () => {
  it("draws the four cells the site read, each with its ids", () => {
    renderReport(REPORT);

    expect(
      ["recovered", "missed", "admitted", "excluded"].map(
        (name) => within(cell(name)).getByTestId("separation-count").textContent,
      ),
    ).toEqual(["61", "19", "2", "38"]);
    expect(within(cell("admitted")).getByTestId("separation-ids").textContent).toBe(
      "PF3D7_0508800, PF3D7_1411400",
    );
  });

  it("says what each criterion adds and what its own step returned", () => {
    renderReport(REPORT);

    const rows = within(screen.getByTestId("separation-criteria"))
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.textContent);
    expect(rows).toEqual([
      "GO Term: GO:0044217 other organism partrecovers 42 of 80 positives, admits 0 of 40 negativeswithout it: -4 positives, 0 negatives",
      "Gene Lists from PlasmoAP motif for protein export to the apicoplast.recovers 31 of 80 positives, admits 2 of 40 negativeswithout it: -13 positives, -2 negatives",
      "GO Term: GO:0051701 biological process involved in interaction with hostrecovers 38 of 80 positives, admits 0 of 40 negativeswithout it: -3 positives, 0 negatives",
    ]);
  });

  it("draws the tree in the strategy's own words", () => {
    renderReport(REPORT);

    expect(screen.getByTestId("separation-tree").textContent).toBe(
      "UnionUnionGO Term: GO:0044217 other organism partGene Lists from " +
        "PlasmoAP motif for protein export to the apicoplast.GO Term: GO:0051701 " +
        "biological process involved in interaction with host",
    );
  });

  it("counts the informative searches, the skipped ones and the requests", () => {
    renderReport(REPORT);

    expect(screen.getByTestId("separation-informative").textContent).toBe(
      "17 of 20 measured searches tell the positives from the negatives",
    );
    expect(screen.getByTestId("separation-requests").textContent).toBe(
      "384 of 400 requests",
    );
    expect(
      screen.getAllByTestId("separation-skipped").map((row) => row.textContent),
    ).toEqual([
      "over the request budget: 1",
      "needs a study analysis: 1",
      "reads another step's result: 1",
      "needs a value only you can set: 5",
      "refused by the site: 7",
      "informs neither: 3",
    ]);
  });

  it("states the shortfall and captions the counts", () => {
    renderReport(REPORT);

    expect(
      screen.getAllByTestId("separation-shortfall").map((line) => line.textContent),
    ).toEqual(REPORT.shortfall);
    expect(REPORT.shortfall?.[2]).toBe(
      "No measured criterion excludes PF3D7_0508800 or PF3D7_1411400 without " +
        "losing a recovered positive.",
    );
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "no strategy separates the sets; closest: 61 of 80 positives, 2 of 40 " +
        "negatives, 1,132 genes, 3 searches; 384 of 400 requests",
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
      "10 more measured searches are not shown.",
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
