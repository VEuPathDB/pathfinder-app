/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { NAC_MISSING_IN_GT1 } from "./__fixtures__/recordedAudits";
import { locusFeatures, placeLocus } from "./locusFeatures";
import { LocusFigure } from "./LocusFigure";

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

  it("adds a gene model that overlaps the span", () => {
    const features = locusFeatures({
      ...NAC_MISSING_IN_GT1,
      overlapping: [
        {
          gene: "TGGT1_257080",
          product: "hypothetical protein",
          orthologGroup: "OG7_0000001",
          proteinLength: 120,
          start: 4157000,
          end: 4157400,
          strand: "+",
          pseudo: false,
          geneType: "protein coding",
        },
      ],
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
