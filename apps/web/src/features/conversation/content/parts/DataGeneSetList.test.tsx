/**
 * @vitest-environment jsdom
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ListedGeneSet, ListedGeneSets } from "@pathfinder/shared";

import { DataGeneSetList } from "./DataGeneSetList";

function listed(over: Partial<ListedGeneSet>): ListedGeneSet {
  return {
    id: "gs-1",
    name: "Gametocyte kinases",
    geneCount: 549,
    genesHere: 549,
    savedOn: "plasmodb",
    savedHere: false,
    ...over,
  };
}

const LISTING: ListedGeneSets = {
  siteId: "plasmodb",
  geneSets: [
    listed({ id: "gs-here", name: "Vaccine candidates draft", savedHere: true }),
    listed({
      id: "gs-ortho",
      name: "3D7 strain gaps",
      geneCount: 3,
      genesHere: 2,
      savedOn: "orthomcl",
    }),
    listed({
      id: "gs-portal",
      name: "Apicoplast proteins",
      geneCount: 12,
      genesHere: 12,
      savedOn: "veupathdb",
    }),
  ],
};

function rows(): HTMLElement[] {
  return within(screen.getByTestId("data-gene-set-list")).getAllByRole("listitem");
}

describe("DataGeneSetList", () => {
  it("lists every set by name with its count on the viewing site", () => {
    render(<DataGeneSetList data={LISTING} />);

    expect(rows().map((row) => row.textContent)).toEqual([
      "Vaccine candidates draftThis conversation549 genes",
      "3D7 strain gaps2 of 3 genes here",
      "Apicoplast proteins12 of 12 genes here",
    ]);
  });

  it("draws the icon of the site each set was saved on", () => {
    render(<DataGeneSetList data={LISTING} />);

    expect(
      rows().map((row) =>
        within(row)
          .getByRole("img", { name: /^Saved on / })
          .getAttribute("data-site-id"),
      ),
    ).toEqual(["plasmodb", "orthomcl", "veupathdb"]);
    expect(
      within(rows()[1]!).getByRole("img", { name: "Saved on OrthoMCL" }),
    ).toBeVisible();
  });

  it("captions the card with the count of sets and the viewing site", () => {
    render(<DataGeneSetList data={LISTING} />);

    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "3 gene sets with genes on PlasmoDB",
    );
  });

  it("marks each set out of date with why, in its own row", () => {
    render(
      <DataGeneSetList
        data={{
          siteId: "orthomcl",
          geneSets: [
            listed({ id: "gs-current", name: "Gametocyte kinases" }),
            listed({
              id: "gs-outgrown",
              name: "Vaccine antigens",
              geneCount: 4593,
              genesHere: 4593,
              savedOn: "orthomcl",
              recordNoun: "protein",
              outOfDate: { kind: "above_the_cap", count: 12480, cap: 10000 },
            }),
            listed({
              id: "gs-groups",
              name: "Singletons",
              outOfDate: { kind: "not_genes", recordClass: "group" },
            }),
            listed({
              id: "gs-unnamed",
              name: "Apicoplast proteins",
              outOfDate: { kind: "not_genes", recordClass: "" },
            }),
            listed({
              id: "gs-empty",
              name: "Rhoptry neck proteins",
              outOfDate: { kind: "no_genes" },
            }),
          ],
        }}
      />,
    );

    const marks = screen.getAllByTestId("gene-set-out-of-date");
    expect(marks.map((mark) => mark.textContent)).toEqual([
      "Out of date: the strategy now returns 12,480 proteins, more than the 10,000 a gene set holds",
      "Out of date: the strategy now returns group records, which are not genes",
      "Out of date: the strategy now returns unnamed records, which are not genes",
      "Out of date: the strategy now returns no genes",
    ]);
    expect(
      rows().map((row) => within(row).queryByTestId("gene-set-out-of-date")),
    ).toEqual([null, ...marks]);
  });

  it("counts a set in its own records", () => {
    render(
      <DataGeneSetList
        data={{
          siteId: "orthomcl",
          geneSets: [
            listed({
              geneCount: 4593,
              genesHere: 4593,
              savedOn: "orthomcl",
              recordNoun: "protein",
            }),
          ],
        }}
      />,
    );

    expect(rows().map((row) => row.textContent)).toEqual([
      "Gametocyte kinases4,593 proteins",
    ]);
  });

  it("says so when no saved set holds genes of the viewing site", () => {
    render(<DataGeneSetList data={{ siteId: "toxodb", geneSets: [] }} />);

    expect(screen.queryAllByRole("listitem")).toEqual([]);
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "No saved gene set has genes on ToxoDB",
    );
  });
});
