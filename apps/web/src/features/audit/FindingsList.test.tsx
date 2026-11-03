/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { listAuditFindingsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditFindingsSuspense";
import type { FindingPage } from "@pathfinder/shared/generated/types/FindingPage";
import type { FindingView } from "@pathfinder/shared/generated/types/FindingView";

import { createTestWrapper } from "@/lib/query/testing";

import { SAMPLE_FINDINGS, SAMPLE_RUN_ID, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { filtersFromSearch, findingQuery } from "./findingQuery";
import { FindingsList, findingOutcome, genomeText } from "./FindingsList";

const [FIRST] = SAMPLE_FINDINGS.findings;
if (FIRST === undefined) throw new Error("the sample run holds findings");

function renderList(page: FindingPage, search: string, onPage = vi.fn()) {
  const state = filtersFromSearch(new URLSearchParams(search));
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    listAuditFindingsSuspenseQueryOptions(SAMPLE_RUN_ID, findingQuery(state)).queryKey,
    page,
  );
  render(
    <FindingsList
      runId={SAMPLE_RUN_ID}
      words={SAMPLE_WORDS}
      state={state}
      search={search}
      live={false}
      onPage={onPage}
    />,
    { wrapper: Wrapper },
  );
}

function cells(index: number): (string | null)[] {
  const row = screen.getAllByRole("row")[index];
  if (row === undefined) throw new Error(`no row ${String(index)}`);
  return [...row.querySelectorAll("td")].map((cell) => cell.textContent);
}

describe("FindingsList", () => {
  it("lists the findings by impact with their outcome, genes, genomes, certainty and source", () => {
    renderList(SAMPLE_FINDINGS, "");
    expect(
      screen.getByRole("table", { name: "Findings, by the screen's impact: 10" }),
    ).toBeInTheDocument();
    expect(cells(1)).toEqual([
      "0.5 (reviewed 0.8)",
      "Intact gene called a pseudogene",
      "PfNF54_100037200, PF3D7_1032400",
      "Plasmodium falciparum NF54",
      "High certainty",
      "Random sample",
      "The review keeps the error",
      "Open",
    ]);
    expect(cells(2)[6]).toBe("The review finds no error");
    expect(cells(3)).toEqual([
      "0.25",
      "Model too short",
      "PcyM_0736700, PCYB_074210",
      "Plasmodium cynomolgi strain M, paired with Plasmodium cynomolgi strain B",
      "High certainty",
      "Your gene target",
      "The review keeps the error",
      "Open",
    ]);
    expect(screen.getByRole("row", { name: /PfDd2_LATE/ })).toHaveTextContent(
      "Not checked: not read before the run's deadline",
    );
    const spare = screen.getByRole("row", { name: /PfDd2_SPARE/ });
    expect(spare).toHaveTextContent("Not checked: not in the random sample");
    expect(spare).toHaveTextContent("Not in the random sample");
    expect(spare).toHaveTextContent("Not reviewed");
    expect(spare).toHaveTextContent("Not weighed");
    expect(
      screen.getByRole("link", {
        name: "Open the finding on PfNF54_100037200 and PF3D7_1032400",
      }),
    ).toHaveAttribute("href", `/audits/${SAMPLE_RUN_ID}/findings/1`);
    expect(screen.getByText("Showing 1 to 10 of 10")).toBeInTheDocument();
  });

  it("keeps the filters on the link to a finding and pages with them", async () => {
    const onPage = vi.fn();
    renderList({ ...SAMPLE_FINDINGS, total: 120 }, "?origin=target", onPage);
    expect(
      screen.getByRole("link", {
        name: "Open the finding on PfNF54_100037200 and PF3D7_1032400",
      }),
    ).toHaveAttribute("href", `/audits/${SAMPLE_RUN_ID}/findings/1?origin=target`);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPage).toHaveBeenCalledWith(50);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("says no finding matches", () => {
    renderList({ ...SAMPLE_FINDINGS, total: 0, findings: [] }, "?certainty=low");
    expect(screen.getByText("No finding matches these filters.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });
});

describe("the certainty of a row", () => {
  it("states the effective certainty and none for a rejected finding", () => {
    const page = {
      ...SAMPLE_FINDINGS,
      findings: [
        { ...FIRST, effectiveCertainty: "medium" as const },
        { ...FIRST, id: 2, effectiveCertainty: null },
      ],
    };
    renderList(page, "");
    expect(cells(1)[4]).toBe("Medium certainty");
    expect(cells(2)[4]).toBe("");
  });
});

describe("the words of a finding", () => {
  const with_ = (changes: Partial<FindingView>): FindingView => ({
    ...FIRST,
    ...changes,
  });

  it("names a clean finding and one the check could not judge", () => {
    const clean = with_({
      errorType: null,
      errorTitle: null,
      effectiveErrorTitle: null,
    });
    expect(findingOutcome(clean, SAMPLE_WORDS)).toBe("No error found");
    expect(findingOutcome({ ...clean, judged: false }, SAMPLE_WORDS)).toBe(
      "Not judged",
    );
  });

  it("names a genome never placed and an error in another genome", () => {
    expect(genomeText(with_({ genome: "" }))).toBe("Not placed in a genome");
    expect(genomeText(with_({ genome: "A", screenedGenome: "B" }))).toBe(
      "A (screened in B)",
    );
  });

  it("names the error the review named", () => {
    const retyped = with_({ effectiveErrorTitle: "One gene split into two models" });
    expect(findingOutcome(retyped, SAMPLE_WORDS)).toBe(
      "One gene split into two models",
    );
  });

  it("says a rejected finding was rejected, naming what the check said", () => {
    const rejected = with_({
      effectiveErrorType: null,
      effectiveErrorTitle: null,
      rejectedText: "The review rejected this; the check said: Model too short",
    });
    expect(findingOutcome(rejected, SAMPLE_WORDS)).toBe(
      "The review rejected this; the check said: Model too short",
    );
  });
});
