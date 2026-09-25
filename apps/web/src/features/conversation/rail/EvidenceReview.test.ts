import { describe, expect, it } from "vitest";
import type { SampledGene } from "@pathfinder/shared";

import { sampleCountLine } from "./EvidenceReview";

function sampled(...fits: SampledGene["fits"][]): SampledGene[] {
  return fits.map((fit, index) => ({
    geneId: `PF3D7_010${index}000`,
    product: "rifin",
    organism: "P. falciparum 3D7",
    fits: fit,
    why: "Read from the gene record.",
  }));
}

describe("sampleCountLine", () => {
  it("names the one fit word every sampled gene carries", () => {
    expect(sampleCountLine(sampled(...Array(8).fill("unclear")))).toBe(
      "8 of 8 sampled genes unclear",
    );
    expect(sampleCountLine(sampled("yes", "yes"))).toBe("2 of 2 sampled genes fit");
    expect(sampleCountLine(sampled("no"))).toBe("1 of 1 sampled gene does not fit");
  });

  it("counts each fit word when the genes differ", () => {
    expect(
      sampleCountLine(
        sampled("yes", "unclear", "yes", "yes", "unclear", "yes", "unclear", "yes"),
      ),
    ).toBe("5 fit, 3 unclear");
    expect(sampleCountLine(sampled("no", "unclear", "unclear"))).toBe(
      "0 fit, 1 does not fit, 2 unclear",
    );
  });
});
