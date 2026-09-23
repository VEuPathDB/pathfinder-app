import { describe, expect, it } from "vitest";
import { countNoun } from "./countNoun";

describe("countNoun", () => {
  it("counts a transcript search in genes, as WDK does", () => {
    expect(countNoun("transcript", 1)).toBe("gene");
    expect(countNoun("transcript", 71)).toBe("genes");
  });

  it("counts a gene search in genes", () => {
    expect(countNoun("gene", 1)).toBe("gene");
    expect(countNoun("gene", 0)).toBe("genes");
  });

  it("names another record type by its own name", () => {
    expect(countNoun("popset_sequence", 3)).toBe("popset sequences");
    expect(countNoun("organism", 1)).toBe("organism");
  });

  it("says results when the record type is unknown", () => {
    expect(countNoun(null, 2)).toBe("results");
    expect(countNoun("", 1)).toBe("result");
  });
});
