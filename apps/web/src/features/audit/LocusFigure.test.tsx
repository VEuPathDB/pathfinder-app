/**
 * @vitest-environment jsdom
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { NAC_MISSING_IN_GT1 } from "./__fixtures__/recordedAudits";
import { locusFeatures, placeLocus } from "./locusFeatures";
import { LocusFigure } from "./LocusFigure";

const PARTIAL_LOCATED = {
  windows: 34,
  found: 12,
  span: [4156680, 4157729] as [number, number],
  ns: 0,
  share: 0.353,
};

const OVERLAPPING = {
  gene: "TGGT1_257080",
  product: "hypothetical protein",
  orthologGroup: "OG7_0000001",
  proteinLength: 120,
  start: 4157000,
  end: 4157400,
  strand: "+" as const,
  pseudo: false,
  geneType: "protein coding",
};

describe("the locus of a missing gene", () => {
  it("places the conserved neighbours and the encoded span on the contig", () => {
    const features = locusFeatures(NAC_MISSING_IN_GT1);
    expect(
      features.map((feature) => [
        feature.kind,
        feature.label,
        feature.start,
        feature.end,
        feature.strand,
      ]),
    ).toEqual([
      ["anchor", "TGGT1_257070", 4176004, 4180213, "-"],
      ["anchor", "TGGT1_257100", 4153116, 4154810, "+"],
      ["found", "Where the DNA encodes TGARI_257090", 4156680, 4157729, null],
    ]);
    const placed = placeLocus(features, 600);
    expect(placed.window).toEqual([4153116, 4180213]);
    expect(placed.features[2]?.x).toBeCloseTo(78.9165, 3);
    expect(placed.features[2]?.width).toBeCloseTo(23.228, 3);
    render(<LocusFigure audit={NAC_MISSING_IN_GT1} />);
    expect(
      screen.getByRole("img", { name: /TGGT1_chrVIIb, bases 4,153,116 to 4,180,213/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "TGGT1_257070, - strand: bases 4,176,004 to 4,180,213",
      "TGGT1_257100, + strand: bases 4,153,116 to 4,154,810",
      "Where the DNA encodes TGARI_257090: bases 4,156,680 to 4,157,729",
    ]);
  });

  it("says encodes only for a verdict that the DNA encodes the gene", () => {
    const partial = { ...NAC_MISSING_IN_GT1, located: PARTIAL_LOCATED };
    for (const verdict of ["PARTIAL", "NOT_IN_DNA", "GAP", "NO_SYNTENY"] as const) {
      expect(locusFeatures({ ...partial, verdict })[2]).toEqual({
        kind: "matched",
        label: "Windows that match, 12 of 34",
        start: 4156680,
        end: 4157729,
        strand: null,
      });
    }
    expect(locusFeatures({ ...partial, verdict: "IN_DNA_OTHER_MODEL" })[2]?.label).toBe(
      "Where the DNA encodes TGARI_257090",
    );
    render(<LocusFigure audit={{ ...partial, verdict: "NOT_IN_DNA" }} />);
    expect(
      screen.getByText(/^Windows that match, 12 of 34: bases/),
    ).toBeInTheDocument();
    expect(screen.getByText("Windows that match")).toBeInTheDocument();
    expect(screen.queryByText(/encodes/)).toBe(null);
  });

  it("points each neighbour's arrow along its strand", () => {
    const { container } = render(<LocusFigure audit={NAC_MISSING_IN_GT1} />);
    expect(
      [...container.querySelectorAll('[data-part="strand"]')].map((arrow) =>
        arrow.getAttribute("points"),
      ),
    ).toEqual(["506.8,10 501.8,15 506.8,20", "37.5,10 42.5,15 37.5,20"]);
  });

  it("paints the encoded span and an overlapping model in tokens that differ in both themes", () => {
    const { container } = render(
      <LocusFigure audit={{ ...NAC_MISSING_IN_GT1, overlapping: [OVERLAPPING] }} />,
    );
    const fill = (part: string) =>
      container.querySelector(`[data-part="${part}"]`)?.getAttribute("fill") ?? "";
    const css = readFileSync(resolve(__dirname, "../../styles/globals.css"), "utf8");
    const values = (paint: string) => {
      const token = /--[a-z0-9-]+/.exec(paint)?.[0] ?? "";
      return [...css.matchAll(new RegExp(`${token}: ([^;]+);`, "g"))].map(
        (match) => match[1],
      );
    };
    const [found, overlap] = [values(fill("found")), values(fill("overlap"))];
    expect(found).toHaveLength(2);
    expect(overlap).toHaveLength(2);
    expect(found[0]).not.toBe(overlap[0]);
    expect(found[1]).not.toBe(overlap[1]);
  });

  it("adds a gene model that overlaps the span", () => {
    const features = locusFeatures({
      ...NAC_MISSING_IN_GT1,
      overlapping: [OVERLAPPING],
    });
    expect(features[3]).toEqual({
      kind: "overlap",
      label: "TGGT1_257080",
      start: 4157000,
      end: 4157400,
      strand: "+",
    });
  });

  it("draws the neighbours alone when the DNA held no span", () => {
    const features = locusFeatures({ ...NAC_MISSING_IN_GT1, located: null });
    expect(features.map((feature) => feature.kind)).toEqual(["anchor", "anchor"]);
  });

  it("draws nothing when the check read no locus", () => {
    const { container } = render(
      <LocusFigure audit={{ ...NAC_MISSING_IN_GT1, anchors: null, located: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
