import { describe, expect, it } from "vitest";

import {
  decodeFilterValue,
  encodeFilterValue,
  summarizeFilterValue,
} from "./filterParamLogic";

const variantsFromSix = {
  field: "total_variants",
  type: "number",
  isRange: true,
  includeUnknown: false,
  value: { min: 6 },
} as const;

describe("filter value codec", () => {
  it("encodes no filters as the value WDK defaults a filter parameter to", () => {
    expect(encodeFilterValue({ filters: [] })).toBe('{"filters":[]}');
  });

  it("keeps a number range clause it decodes", () => {
    const decoded = decodeFilterValue(JSON.stringify({ filters: [variantsFromSix] }));

    expect(decoded).toEqual({ parsed: { filters: [variantsFromSix] }, ok: true });
  });

  it("refuses a clause that names no type", () => {
    const untyped = {
      field: "organism",
      isRange: false,
      includeUnknown: false,
      value: ["a"],
    };

    expect(decodeFilterValue(JSON.stringify({ filters: [untyped] })).ok).toBe(false);
  });

  it("refuses a bare list of clauses", () => {
    expect(decodeFilterValue(JSON.stringify([variantsFromSix])).ok).toBe(false);
  });
});

describe("summarizeFilterValue", () => {
  it("writes an open upper bound in ASCII", () => {
    expect(summarizeFilterValue(variantsFromSix)).toBe("6 - +inf");
  });

  it("writes an open lower bound in ASCII", () => {
    expect(
      summarizeFilterValue({
        field: "release_date",
        type: "date",
        isRange: true,
        includeUnknown: false,
        value: { max: "2014-08-30" },
      }),
    ).toBe("-inf - 2014-08-30");
  });

  it("names the first three members and counts the rest", () => {
    expect(
      summarizeFilterValue({
        field: "organism",
        type: "string",
        isRange: false,
        includeUnknown: false,
        value: ["a", "b", "c", "d", "e"],
      }),
    ).toBe("a, b, c +2 more");
  });

  it("names the operation and leaves of a compound clause", () => {
    expect(
      summarizeFilterValue({
        field: "snps",
        type: "multiFilter",
        isRange: false,
        includeUnknown: false,
        value: {
          operation: "union",
          filters: [
            {
              field: "s1",
              type: "string",
              isRange: false,
              includeUnknown: false,
              value: ["x"],
            },
          ],
        },
      }),
    ).toBe("union of 1 filter");
  });
});
