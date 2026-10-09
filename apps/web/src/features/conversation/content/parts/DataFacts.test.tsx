/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { TurnFacts } from "@pathfinder/shared";

import { DataFacts } from "./DataFacts";

const URL =
  "https://qa.amoebadb.org/amoeba.qa/app/workspace/strategies/440299573/440299574";
const TOXO_RECORD = "https://qa.toxodb.org/toxo.qa/app/record/gene";
const CLAUSE =
  "Minimum expression percentile at the site's default of 80: 1,665 genes; at 0: 8,201";

const FACTS: TurnFacts = {
  recordNoun: "gene",
  steps: [
    {
      stepId: "s_go",
      displayName: "GO Term",
      count: 220,
      reason: "peptidase activity: no other search names the activity",
      parameters: [
        {
          name: "GoTerm",
          displayName: "GO term",
          value: "GO:0008234",
          label: "cysteine-type peptidase activity",
          source: "stated",
        },
      ],
    },
    {
      stepId: "s_rna",
      displayName: "Trophozoite RNA-Seq percentile",
      count: 1665,
      parameters: [
        {
          name: "min_expression_percentile",
          displayName: "Minimum expression percentile",
          value: "80",
          source: "default",
          notes: [CLAUSE],
        },
      ],
    },
    { stepId: "s_and", displayName: "Combine", operator: "INTERSECT", count: 74 },
  ],
  rootCount: 74,
  strategyUrl: URL,
  caveats: [
    {
      kind: "controls",
      positivesReturned: 7,
      positivesTotal: 10,
      negativesReturned: 0,
      negativesTotal: 5,
      sentence: "7 of 10 positive controls returned",
    },
  ],
  gaps: [
    {
      kind: "word",
      word: "pseudogenes",
      sentence: "'pseudogenes': no search the strategy runs states it",
    },
  ],
  retired: [
    {
      requirement: "above the 50th percentile",
      state: "withdrawn",
      sentence: "'above the 50th percentile' is withdrawn",
    },
  ],
  saved: [{ kind: "gene_set", name: "peptidases draft", count: 74 }],
  refusal: "status_code: 400, the provider refused the request whole",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DataFacts", () => {
  it("shows each step in tree order with its count", () => {
    render(<DataFacts data={FACTS} />);

    const steps = screen.getAllByTestId("facts-step");
    expect(
      steps.map((row) => within(row).getByTestId("facts-step-name").textContent),
    ).toEqual(["GO Term", "Trophozoite RNA-Seq percentile", "INTERSECTCombine"]);
    expect(
      steps.map((row) => within(row).getByTestId("facts-step-count").textContent),
    ).toEqual(["220 genes", "1,665 genes", "74 genes"]);
    expect(screen.getByTestId("facts-root-count")).toHaveTextContent(
      "Result: 74 genes",
    );
  });

  it("shows why a step runs its search under its name", () => {
    render(<DataFacts data={FACTS} />);

    expect(screen.getByTestId("facts-step-reason")).toHaveTextContent(
      "peptidase activity: no other search names the activity",
    );
  });

  it("shows who set each value and the measurement of a default", () => {
    render(<DataFacts data={FACTS} />);

    const params = screen.getAllByTestId("facts-param");
    expect(params.map((row) => row.getAttribute("data-source"))).toEqual([
      "stated",
      "default",
    ]);
    expect(params[0]).toHaveTextContent(
      "GO:0008234 (cysteine-type peptidase activity)",
    );
    expect(within(params[1]!).getByTestId("facts-param-note")).toHaveTextContent(
      CLAUSE,
    );
  });

  it("shows caveats, gaps and withdrawn requirements as their sentences", () => {
    render(<DataFacts data={FACTS} />);

    expect(screen.getByTestId("facts-caveat")).toHaveTextContent(
      "7 of 10 positive controls returned",
    );
    expect(screen.getByTestId("facts-gap")).toHaveTextContent("'pseudogenes'");
    expect(screen.getByTestId("facts-retired")).toHaveTextContent(
      "'above the 50th percentile' is withdrawn",
    );
  });

  it("links the strategy and names the set this turn saved", () => {
    render(<DataFacts data={FACTS} />);

    expect(screen.getByTestId("facts-strategy-link")).toHaveAttribute("href", URL);
    expect(screen.getByTestId("facts-saved-set")).toHaveTextContent(
      "Saved gene set peptidases draft, 74 genes",
    );
  });

  it("opens the strategy and the records in a new tab inside the website page", () => {
    vi.spyOn(window, "top", "get").mockReturnValue(null);
    render(<DataFacts data={FACTS} />);

    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("target"))).toEqual(
      links.map(() => "_blank"),
    );
    expect(links.map((a) => a.getAttribute("rel"))).toEqual(
      links.map(() => "noreferrer"),
    );
  });

  it("shows a refusal whole", () => {
    render(<DataFacts data={FACTS} />);

    expect(screen.getByTestId("facts-refusal")).toHaveTextContent(
      "status_code: 400, the provider refused the request whole",
    );
  });

  it("shows a leaf's record under the leaf with its fit, not under the result", () => {
    const record = "https://qa.toxodb.org/toxo.qa/app/record/gene/TGME49_200010";
    render(
      <DataFacts
        data={{
          steps: [
            { stepId: "step_d2536be6", displayName: "SignalP", count: 627 },
            { stepId: "step_root", displayName: "Minus", operator: "MINUS", count: 9 },
          ],
          rootCount: 9,
          sources: [
            {
              url: record,
              recordId: "TGME49_200010",
              product: "hypothetical protein",
              stepId: "step_d2536be6",
              stepName: "SignalP",
              fit: "unclear",
            },
            { url: "https://doi.org/10.1016/j.cell.2008.01.001" },
          ],
        }}
      />,
    );

    const [leaf, root] = screen.getAllByTestId("facts-step");
    const source = within(leaf!).getByTestId("facts-source");
    expect(source).toHaveTextContent(
      "TGME49_200010, hypothetical protein (the check judged its fit unclear)",
    );
    expect(within(source).getByRole("link")).toHaveAttribute("href", record);
    expect(within(root!).queryByTestId("facts-source")).toBeNull();
    expect(screen.getAllByTestId("facts-source")).toHaveLength(2);
  });

  it("shows the count an edit moved beside the count before it", () => {
    render(
      <DataFacts
        data={{
          steps: [
            {
              stepId: "c_text",
              displayName: "Text search",
              count: 19,
              countBefore: 2160,
            },
          ],
          rootCount: 19,
          rootCountBefore: 2160,
        }}
      />,
    );

    expect(screen.getByTestId("facts-step-count")).toHaveTextContent(
      "19 genes, 2,160 genes before this turn's edit",
    );
    expect(screen.getByTestId("facts-root-count")).toHaveTextContent(
      "Result: 19 genes, 2,160 genes before this turn's edit",
    );
  });

  it("shows the last change with the result's count before and after it", () => {
    render(
      <DataFacts
        data={{
          rootCount: 68,
          lastChange: {
            what: "deleted Predicted Signal Peptide",
            before: 17,
            after: 68,
          },
        }}
      />,
    );

    expect(screen.getByTestId("facts-last-change")).toHaveTextContent(
      "Last change: deleted Predicted Signal Peptide; 17 genes before, 68 genes after",
    );
  });

  it("says a count the last change did not record is not recorded", () => {
    render(
      <DataFacts
        data={{
          rootCount: 68,
          lastChange: { what: "built the strategy", after: 68 },
        }}
      />,
    );

    expect(screen.getByTestId("facts-last-change")).toHaveTextContent(
      "Last change: built the strategy; count before not recorded, 68 genes after",
    );
  });

  it("lists the genes the message names with their records", () => {
    const record = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1133400";
    render(
      <DataFacts
        data={{
          namedGenes: [
            {
              url: record,
              recordId: "PF3D7_1133400",
              product: "apical membrane antigen 1",
              organism: "P. falciparum 3D7",
            },
          ],
        }}
      />,
    );

    const named = screen.getByTestId("facts-named-gene");
    expect(named).toHaveTextContent(
      "PF3D7_1133400, apical membrane antigen 1, P. falciparum 3D7",
    );
    expect(within(named).getByRole("link")).toHaveAttribute("href", record);
  });

  it("lists the ids a listing returned under the step it listed", () => {
    render(
      <DataFacts
        data={{
          steps: [
            { stepId: "step_hha", displayName: "Text search", count: 23 },
            { stepId: "step_join", displayName: "Intersect", count: 19 },
          ],
          listed: [
            {
              stepId: "step_hha",
              stepName: "Text search",
              records: [
                { recordId: "HHA_208730", url: `${TOXO_RECORD}/HHA_208730` },
                { recordId: "HHA_208740", url: `${TOXO_RECORD}/HHA_208740` },
              ],
            },
          ],
        }}
      />,
    );

    const [leaf, root] = screen.getAllByTestId("facts-step");
    const listed = within(leaf!).getByTestId("facts-listed");
    expect(listed).toHaveTextContent("Listed from Text search: HHA_208730, HHA_208740");
    expect(
      within(listed)
        .getAllByRole("link")
        .map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      ["HHA_208730", `${TOXO_RECORD}/HHA_208730`],
      ["HHA_208740", `${TOXO_RECORD}/HHA_208740`],
    ]);
    expect(within(root!).queryByTestId("facts-listed")).toBeNull();
  });

  it("shows a record's other words beside its product", () => {
    render(
      <DataFacts
        data={{
          sources: [
            {
              url: "https://qa.tritrypdb.org/tritrypdb.qa/app/record/gene/Tbg972.6.590",
              recordId: "Tbg972.6.590",
              product: "hypothetical protein",
              values: ["chromosome 6"],
            },
          ],
        }}
      />,
    );

    expect(screen.getByTestId("facts-source")).toHaveTextContent(
      "Tbg972.6.590, hypothetical protein, chromosome 6",
    );
  });

  it("draws nothing for a kind the turn does not hold", () => {
    render(<DataFacts data={{ steps: [], rootCount: null }} />);

    expect(screen.getByTestId("data-facts")).toBeInTheDocument();
    expect(screen.queryByTestId("facts-step")).toBeNull();
    expect(screen.queryByTestId("facts-root-count")).toBeNull();
    expect(screen.queryByTestId("facts-strategy-link")).toBeNull();
  });
});
