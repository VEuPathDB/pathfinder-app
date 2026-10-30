/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { TurnFacts } from "@pathfinder/shared";

import { DataFacts } from "./DataFacts";
import { DataFactsNotices } from "./DataFactsNotices";

const PLASMO_RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene";

afterEach(cleanup);

describe("the facts a read without a strategy step shows", () => {
  it("draws a count that no card shows, with its noun", () => {
    const data: TurnFacts = {
      recordNoun: "gene",
      comparisons: [
        {
          onItsCard: false,
          variants: [{ label: "Signal peptide", geneCount: 479 }],
        },
        {
          onItsCard: true,
          variants: [{ label: "On its card", geneCount: 12 }],
        },
      ],
    };
    render(<DataFacts data={data} />);

    expect(screen.getAllByTestId("facts-count").map((row) => row.textContent)).toEqual([
      "Signal peptide: 479 genes",
    ]);
  });

  it("draws which asked genes a search holds, each linked to its page", () => {
    const records = ["PF3D7_1315100", "PF3D7_0500900", "PF3D7_1444500"].map((id) => ({
      recordId: id,
      url: `${PLASMO_RECORD}/${id}`,
    }));
    const data: TurnFacts = {
      memberships: [
        {
          searchLabel: "Signal peptide",
          records,
          held: ["PF3D7_1315100"],
          unread: ["PF3D7_1444500"],
        },
      ],
    };
    render(<DataFacts data={data} />);

    const membership = screen.getByTestId("facts-membership");
    const rows = within(membership)
      .getAllByRole("listitem")
      .map((row) => row.textContent);
    expect(rows).toEqual([
      "Held by Signal peptide: PF3D7_1315100",
      "Not held by Signal peptide: PF3D7_0500900",
      "Past the read of Signal peptide: PF3D7_1444500",
    ]);
    expect(
      within(membership)
        .getByRole("link", { name: "PF3D7_0500900" })
        .getAttribute("href"),
    ).toBe(`${PLASMO_RECORD}/PF3D7_0500900`);
  });

  it("draws an audit finding with its certainty and its evidence", () => {
    const data: TurnFacts = {
      reads: [
        {
          title: "Finding 1 of audit run 16bffc57-95c8-4ed1-9e61-4813cdcd0e09",
          rows: [
            { label: "finding error title", value: "Splice site shifted" },
            { label: "finding certainty", value: "medium" },
            { label: "evidence kind", value: "confirmation" },
            { label: "evidence status", value: "stored" },
          ],
        },
      ],
    };
    render(<DataFacts data={data} />);

    const audit = screen.getByTestId("facts-read");
    expect(
      within(audit).getByText(/^Finding 1 of audit run 16bffc57/).textContent,
    ).toBe("Finding 1 of audit run 16bffc57-95c8-4ed1-9e61-4813cdcd0e09");
    expect(
      within(audit)
        .getAllByTestId("facts-read-row")
        .map((row) => row.textContent),
    ).toEqual([
      "finding error title: Splice site shifted",
      "finding certainty: medium",
      "evidence kind: confirmation",
      "evidence status: stored",
    ]);
  });

  it("draws a records-organism caveat through the caveat list", () => {
    const sentence =
      "The strategy's records are genes of Plasmodium vivax P01; the seed searched Plasmodium falciparum 3D7";
    const data: TurnFacts = {
      caveats: [
        {
          kind: "records_organism",
          records: ["Plasmodium vivax P01"],
          seed: ["Plasmodium falciparum 3D7"],
          sentence,
        },
      ],
    };
    render(<DataFacts data={data} />);

    const caveat = screen.getByTestId("facts-caveat");
    expect([caveat.getAttribute("data-kind"), caveat.textContent]).toEqual([
      "records_organism",
      sentence,
    ]);
  });
});

describe("the failed check notice", () => {
  it("states the last check's failure with its reason", () => {
    const failed =
      "The last check of this strategy failed: Seven of eight sampled genes are not odorant-binding proteins.";
    render(<DataFactsNotices data={{ failedCheck: failed }} />);

    expect(screen.getByTestId("facts-failed-check").textContent).toBe(failed);
  });
});
