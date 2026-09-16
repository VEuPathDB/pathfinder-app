import { describe, expect, it } from "vitest";
import type { ParamSpec } from "@pathfinder/shared";

import { organismParamOf } from "./organismParam";

type Vocabulary = NonNullable<ParamSpec["vocabulary"]> | null;

const SITE_ORGANISMS = [
  "Plasmodium berghei ANKA",
  "Plasmodium falciparum 3D7",
  "Plasmodium vivax P01",
];

function taxonTree(): Vocabulary {
  return {
    data: { term: "@@fake@@", display: "All" },
    children: [
      {
        data: { term: "Plasmodium", display: "Plasmodium" },
        children: [
          {
            data: {
              term: "Plasmodium falciparum 3D7",
              display: "P. falciparum 3D7",
            },
          },
          { data: { term: "Plasmodium berghei ANKA", display: "P. berghei ANKA" } },
        ],
      },
    ],
  };
}

function spec(name: string, vocabulary: Vocabulary): ParamSpec {
  return { name, type: "enum", vocabulary };
}

describe("organismParamOf", () => {
  it("names the parameter whose vocabulary is the site's organisms", () => {
    const specs = [
      spec("min_transcript_length", null),
      spec("text_search_organism", taxonTree()),
    ];

    expect(organismParamOf(specs, SITE_ORGANISMS)).toEqual({
      name: "text_search_organism",
      organisms: ["Plasmodium falciparum 3D7", "Plasmodium berghei ANKA"],
    });
  });

  it("keeps only the terms the site declares as organisms", () => {
    const found = organismParamOf([spec("organism", taxonTree())], SITE_ORGANISMS);

    expect(found?.organisms).not.toContain("Plasmodium");
    expect(found?.organisms).not.toContain("@@fake@@");
  });

  it("skips a parameter whose vocabulary names no organism", () => {
    const specs = [
      spec("sequence_type", [
        ["genomic", "Genomic", null],
        ["protein", "Protein", null],
      ]),
      spec("organism", taxonTree()),
    ];

    expect(organismParamOf(specs, SITE_ORGANISMS)?.name).toBe("organism");
  });

  it("names nothing when the search declares no organism vocabulary", () => {
    const specs = [spec("gene_ids", null), spec("min_transcript_length", null)];

    expect(organismParamOf(specs, SITE_ORGANISMS)).toBe(null);
  });

  it("names nothing when the site declares no organisms", () => {
    expect(organismParamOf([spec("organism", taxonTree())], [])).toBe(null);
  });
});
