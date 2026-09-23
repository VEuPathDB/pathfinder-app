import { describe, expect, it } from "vitest";
import type { ParamSpec } from "@pathfinder/shared";
import { hiddenParamDefaults } from "./useStepParameters";

function spec(over: Partial<ParamSpec> & { name: string }): ParamSpec {
  return {
    type: "string",
    displayName: over.name,
    displayType: "",
    allowEmptyValue: true,
    isVisible: false,
    isNumber: false,
    countOnlyLeaves: false,
    initialDisplayValue: "",
    ...over,
  };
}

describe("hiddenParamDefaults", () => {
  it("gives the parameter that wires a step's input no default", () => {
    const defaults = hiddenParamDefaults([
      spec({ name: "gene_result", type: "input-step", group: "_hidden" }),
    ]);

    expect(defaults).toEqual({});
  });

  it("keeps the initial value of another hidden parameter", () => {
    const defaults = hiddenParamDefaults([
      spec({ name: "gene_result", type: "input-step" }),
      spec({ name: "document_type", initialDisplayValue: "gene" }),
      spec({ name: "organism", isVisible: true, initialDisplayValue: "Pf3D7" }),
    ]);

    expect(defaults).toEqual({ document_type: "gene" });
  });
});
