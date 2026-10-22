/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { ColumnTally } from "@pathfinder/shared";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataColumnTally } from "./DataColumnTally";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const ORGANISMS = [
  "Aedes aegypti LVP_AGWG",
  "Anopheles gambiae PEST",
  "Aedes albopictus Foshan FPA",
  "Anopheles stephensi UCISS2018",
  "Anopheles coluzzii AcolN3",
  "Culex quinquefasciatus JHB 2020",
  "Anopheles quadriannulatus SANGWE",
  "Anopheles sinensis SINENSIS",
  "Anopheles arabiensis DONGOLA 2021",
  "Anopheles funestus FUMOZ",
  "Anopheles merus MAF 2021",
  "Glossina morsitans Yale",
];

const TALLY: ColumnTally = {
  id: "tally_0a1b2c3d",
  title: "Datasets by Organism(s), where Category is RNASeq",
  searchName: "AllDatasets",
  recordType: "dataset",
  recordNoun: "dataset",
  column: "organism_prefix",
  columnLabel: "Organism(s)",
  only: { column: "newcategory", values: ["RNASeq"] },
  onlyLabel: "Category",
  total: 379,
  distinct: 58,
  missing: 0,
  rows: ORGANISMS.map((value, index) => ({ value, count: 67 - index * 5, label: "" })),
  siteId: "vectorbase",
  stepUrl: null,
};

const STEP_URL =
  "https://qa.orthomcl.org/orthomcl.qa/app/workspace/strategies/1188/227284080";

const PROTEINS: ColumnTally = {
  id: "tally_5e6f7a8b",
  title: "Proteins by Taxon Code",
  searchName: "FromGroups",
  recordType: "sequence",
  recordNoun: "protein",
  column: "abbreviation",
  columnLabel: "Taxon Code",
  onlyLabel: "",
  total: 523795,
  distinct: 840,
  missing: 0,
  rows: [
    { value: "bpli", count: 18260, label: "Brachionus plicatilis" },
    { value: "osat", count: 9365, label: "Oryza sativa Japonica Group" },
  ],
  siteId: "orthomcl",
  stepUrl: STEP_URL,
};

function inThread(data: ColumnTally = TALLY) {
  const messages = threadOf([threadPart("data-column-tally", data)]);
  return render(
    <ChatHelpersProvider value={chatHelpersFor(messages)}>
      <DataColumnTally data={data} />
    </ChatHelpersProvider>,
  );
}

describe("DataColumnTally", () => {
  it("is a numbered table titled by what it counted", () => {
    inThread();

    const card = screen.getByTestId("data-column-tally");
    expect(card).toHaveTextContent("Datasets by Organism(s), where Category is RNASeq");
    expect(screen.getByTestId("figure-caption")).toHaveTextContent(
      "Table 1. 379 datasets, 58 values, the 12 with the most shown",
    );
  });

  it("heads the values with the column and the counts with the noun", () => {
    inThread();

    expect(screen.getAllByRole("columnheader").map((head) => head.textContent)).toEqual(
      ["Organism(s)", "Datasets"],
    );
  });

  it("shows the counts most first, ten a page", () => {
    inThread();

    const rows = screen.getAllByTestId("tally-row");
    expect(rows).toHaveLength(10);
    expect(
      within(rows[0]!)
        .getAllByRole("cell")
        .map((c) => c.textContent),
    ).toEqual(["Aedes aegypti LVP_AGWG", "67"]);
    expect(screen.getByTestId("exhibit-pager")).toHaveTextContent("1-10 of 12");
  });

  it("names each counted code beside its value", () => {
    inThread(PROTEINS);

    const first = screen.getAllByTestId("tally-row")[0]!;
    expect(within(first).getByTestId("tally-value")).toHaveTextContent("bpli");
    expect(within(first).getByTestId("tally-label")).toHaveTextContent(
      "Brachionus plicatilis",
    );
    expect(within(first).getAllByRole("cell")[1]).toHaveTextContent("18,260");
  });

  it("heads a counted step's proteins with their noun", () => {
    inThread(PROTEINS);

    expect(screen.getAllByRole("columnheader").map((head) => head.textContent)).toEqual(
      ["Taxon Code", "Proteins"],
    );
  });

  it("links the counted step on its site", () => {
    inThread(PROTEINS);

    const link = screen.getByRole("link", { name: "Open this step on OrthoMCL" });
    expect(link).toHaveAttribute("href", STEP_URL);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("draws no link and no label for a search counted without a step", () => {
    inThread();

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByTestId("tally-label")).toBeNull();
    expect(
      within(screen.getAllByTestId("tally-row")[0]!)
        .getAllByRole("cell")
        .map((c) => c.textContent),
    ).toEqual(["Aedes aegypti LVP_AGWG", "67"]);
  });
});
