import { describe, expect, it } from "vitest";

import { formatParamValue, type ParamValue } from "./paramValue";

describe("formatParamValue", () => {
  it("reads a text value as the text itself", () => {
    expect(formatParamValue({ type: "string", value: "gametocyte" })).toBe(
      "gametocyte",
    );
  });

  it("reads a vocabulary pick as the term", () => {
    expect(
      formatParamValue({ type: "single-pick-vocabulary", value: "P. falciparum" }),
    ).toBe("P. falciparum");
  });

  it("joins a multi-pick with commas", () => {
    expect(
      formatParamValue({ type: "multi-pick-vocabulary", values: ["ring", "schizont"] }),
    ).toBe("ring, schizont");
  });

  it("says none when a multi-pick holds nothing", () => {
    expect(formatParamValue({ type: "multi-pick-vocabulary", values: [] })).toBe(
      "(none)",
    );
  });

  it("reads a number as the number", () => {
    expect(formatParamValue({ type: "number", value: 1.3 })).toBe("1.3");
  });

  it("reads a closed number range as min to max", () => {
    expect(formatParamValue({ type: "number-range", min: 2, max: 8 })).toBe("2 to 8");
  });

  it("names the open end of a half-bounded range", () => {
    expect(formatParamValue({ type: "number-range", min: 2, max: null })).toBe(
      "2 or more",
    );
    expect(formatParamValue({ type: "number-range", min: null, max: 8 })).toBe(
      "8 or less",
    );
  });

  it("reads a date range as min to max", () => {
    expect(
      formatParamValue({ type: "date-range", min: "2026-01-01", max: "2026-12-31" }),
    ).toBe("2026-01-01 to 2026-12-31");
  });

  it("reads a date and a timestamp as the stored value", () => {
    expect(formatParamValue({ type: "date", value: "2026-01-01" })).toBe("2026-01-01");
    expect(formatParamValue({ type: "timestamp", value: "1767225600" })).toBe(
      "1767225600",
    );
  });

  it("names the dataset and the step a value points at", () => {
    expect(formatParamValue({ type: "input-dataset", datasetId: "ds-7" })).toBe("ds-7");
    expect(formatParamValue({ type: "input-step", stepId: "step-3" })).toBe("step-3");
  });

  it("counts a filter's clauses and names their fields", () => {
    const filter: ParamValue = {
      type: "filter",
      filters: [
        { field: "organism", value: ["P. falciparum"] },
        { field: "stage", value: ["ring"] },
      ],
    };
    expect(formatParamValue(filter)).toBe("2 filters (organism, stage)");
  });

  it("says no filters when a filter value is empty", () => {
    expect(formatParamValue({ type: "filter", filters: [] })).toBe("(no filters)");
  });

  it("says any when both ends of a range are open", () => {
    expect(formatParamValue({ type: "number-range", min: null, max: null })).toBe(
      "(any)",
    );
  });
});
