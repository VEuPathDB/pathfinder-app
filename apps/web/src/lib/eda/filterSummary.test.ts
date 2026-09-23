import { describe, expect, it } from "vitest";

import { filterSummary } from "./filterSummary";

const FEBRILE = {
  entityId: "ENT_8151325d",
  variableId: "VAR_081ab087",
  type: "stringSet" as const,
  stringSet: ["febrile"],
};

describe("filterSummary", () => {
  it("summarises a stringSet by its values", () => {
    expect(filterSummary(FEBRILE)).toBe("febrile");
  });

  it("summarises a long stringSet by count", () => {
    expect(filterSummary({ ...FEBRILE, stringSet: ["a", "b", "c", "d"] })).toBe(
      "4 values",
    );
  });

  it("summarises a numberRange as an inclusive interval", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "numberRange",
        min: 37,
        max: 42,
      }),
    ).toBe("37 to 42");
  });

  it("summarises a dateRange without its time part", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "dateRange",
        min: "2017-05-05T00:00:00",
        max: "2017-05-11T00:00:00",
      }),
    ).toBe("2017-05-05 to 2017-05-11");
  });

  it("summarises a numberSet by its values", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "numberSet",
        numberSet: [1, 2],
      }),
    ).toBe("1, 2");
  });

  it("summarises a dateSet by its size", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "dateSet",
        dateSet: ["2017-05-05T00:00:00"],
      }),
    ).toBe("1 dates");
  });

  it("summarises a longitudeRange by its two edges", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "longitudeRange",
        left: -10,
        right: 20,
      }),
    ).toBe("-10 to 20");
  });

  it("summarises a multiFilter by its operation and sub-filter count", () => {
    expect(
      filterSummary({
        entityId: "E",
        variableId: "V",
        type: "multiFilter",
        operation: "union",
        subFilters: [
          { variableId: "A", stringSet: ["Yes"] },
          { variableId: "B", stringSet: ["Yes"] },
        ],
      }),
    ).toBe("union of 2");
  });
});
