import { describe, expect, it } from "vitest";

import type { ParamSpec } from "@pathfinder/shared";

import { resolveWidgetKind } from "./registry";

function stringSpec(name: string): ParamSpec {
  return {
    name,
    type: "string",
    displayName: "Filter genes based on phenotype data",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
  };
}

describe("resolveWidgetKind", () => {
  it("gives the EDA analysis spec its own widget", () => {
    expect(resolveWidgetKind(stringSpec("eda_analysis_spec"))).toBe("eda-spec");
  });

  it("keeps an ordinary string parameter on the text field", () => {
    expect(resolveWidgetKind(stringSpec("text_expression"))).toBe("string");
  });
});
