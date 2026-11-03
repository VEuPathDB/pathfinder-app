import { describe, expect, it } from "vitest";

import { filtersFromSearch, findingQuery, searchFromFilters } from "./findingFilters";

describe("finding filters", () => {
  it("reads the filters from the address and drops what it does not know", () => {
    const state = filtersFromSearch(
      new URLSearchParams(
        "check=gene_length&origin=target&offset=50&certainty=certain&genome=Plasmodium+falciparum+Dd2",
      ),
    );
    expect(state).toEqual({
      check: "gene_length",
      screenedGenome: null,
      genome: "Plasmodium falciparum Dd2",
      errorType: null,
      certainty: null,
      origin: "target",
      offset: 50,
    });
    expect(searchFromFilters(state)).toBe(
      "?check=gene_length&genome=Plasmodium+falciparum+Dd2&origin=target&offset=50",
    );
    expect(searchFromFilters(filtersFromSearch(new URLSearchParams("offset=-3")))).toBe(
      "",
    );
    expect(filtersFromSearch(new URLSearchParams("offset=1.5")).offset).toBe(0);
  });

  it("asks the API for the source the reader chose", () => {
    const none = filtersFromSearch(new URLSearchParams());
    expect(findingQuery({ ...none, origin: "sample" })).toEqual({
      sampled: true,
      target: false,
      offset: 0,
      limit: 50,
    });
    expect(findingQuery({ ...none, origin: "unsampled" })).toEqual({
      sampled: false,
      offset: 0,
      limit: 50,
    });
    expect(findingQuery({ ...none, origin: "target", certainty: "high" })).toEqual({
      certainty: "high",
      target: true,
      offset: 0,
      limit: 50,
    });
  });
});
