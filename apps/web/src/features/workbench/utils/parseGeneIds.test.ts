import { describe, it, expect } from "vitest";
import { parseGeneIds } from "./parseGeneIds";

describe("parseGeneIds", () => {
  it("splits on newlines, commas, and tabs", () => {
    expect(parseGeneIds("A\nB,C\tD")).toEqual(["A", "B", "C", "D"]);
  });

  it("trims whitespace", () => {
    expect(parseGeneIds("  A , B \n C ")).toEqual(["A", "B", "C"]);
  });

  it("removes empty entries", () => {
    expect(parseGeneIds("A,,B\n\nC")).toEqual(["A", "B", "C"]);
  });

  it("deduplicates preserving first occurrence order", () => {
    expect(parseGeneIds("A,B,A,C,B")).toEqual(["A", "B", "C"]);
  });

  it("returns empty array for empty input", () => {
    expect(parseGeneIds("")).toEqual([]);
    expect(parseGeneIds("   ")).toEqual([]);
  });
});
