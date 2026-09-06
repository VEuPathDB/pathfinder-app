// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { recordCountLabel } from "./recordCountLabel";

// A gene set of 438 genes rendered "448 records" in the results table
// because WDK counts transcripts. Two unqualified numbers for "how big is
// this set" is a data-integrity question for a researcher; naming the unit
// makes the difference self-explanatory.
describe("recordCountLabel", () => {
  it("names the record type when known", () => {
    expect(recordCountLabel(448, "transcript")).toBe("448 transcripts");
  });

  it("singularizes a count of one", () => {
    expect(recordCountLabel(1, "transcript")).toBe("1 transcript");
  });

  it("handles gene record types", () => {
    expect(recordCountLabel(438, "gene")).toBe("438 genes");
  });

  it("falls back to 'records' when the type is unknown", () => {
    expect(recordCountLabel(448, null)).toBe("448 records");
  });

  it("groups thousands for readability", () => {
    expect(recordCountLabel(2862, "gene")).toBe("2,862 genes");
  });

  it("handles zero", () => {
    expect(recordCountLabel(0, "gene")).toBe("0 genes");
  });

  it("humanizes underscored record types", () => {
    expect(recordCountLabel(3, "popset_sequence")).toBe("3 popset sequences");
  });
});
