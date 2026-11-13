// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { Step } from "@strategist/shared";
import { useStepDraftChanges } from "./useStepDraftChanges";

const single = (value: string) => ({ type: "single-pick-vocabulary" as const, value });
const multi = (values: string[]) => ({
  type: "multi-pick-vocabulary" as const,
  values,
});

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "step-1",
    displayName: "Step 1",
    searchName: "GenesByTaxon",
    recordType: "transcript",
    parameters: { organism: single("Pf3D7") },
    isFiltered: false,
    operator: "",
    colocationParams: null,
    ...overrides,
  };
}

const ALL_PARAMS = new Set(["organism", "min_weight", "go_terms"]);

describe("useStepDraftChanges", () => {
  it("returns zero changes when form values match step parameters", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { organism: single("Pf3D7") } }),
      formValues: { organism: "Pf3D7" },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(0);
    expect(result.changedKeys).toEqual([]);
    expect(result.hasChanges).toBe(false);
  });

  it("detects a single param change", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { organism: single("Pf3D7") } }),
      formValues: { organism: "PvP01" },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(1);
    expect(result.changedKeys).toEqual(["parameters.organism"]);
    expect(result.hasChanges).toBe(true);
  });

  it("detects an added param", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { organism: single("Pf3D7") } }),
      formValues: { organism: "Pf3D7", min_weight: "1000" },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(1);
    expect(result.changedKeys).toEqual(["parameters.min_weight"]);
  });

  it("detects array (multi-pick) param changes", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { go_terms: multi(["GO:0006915"]) } }),
      formValues: { go_terms: ["GO:0006915", "GO:0007049"] },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(1);
    expect(result.changedKeys).toEqual(["parameters.go_terms"]);
  });

  it("treats identical arrays as no change", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { go_terms: multi(["GO:0006915", "GO:0007049"]) } }),
      formValues: { go_terms: ["GO:0006915", "GO:0007049"] },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(0);
  });

  it("detects operator changes", () => {
    const result = useStepDraftChanges({
      step: makeStep({ operator: "INTERSECT" }),
      formValues: { organism: "Pf3D7" },
      operator: "UNION",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(1);
    expect(result.changedKeys).toEqual(["operator"]);
  });

  it("detects displayName changes", () => {
    const result = useStepDraftChanges({
      step: makeStep({ displayName: "Step 1" }),
      formValues: { organism: "Pf3D7" },
      operator: "",
      displayName: "Renamed Step",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(1);
    expect(result.changedKeys).toEqual(["displayName"]);
  });

  it("counts multiple simultaneous changes", () => {
    const result = useStepDraftChanges({
      step: makeStep({
        parameters: { organism: single("Pf3D7") },
        operator: "",
        displayName: "Step 1",
      }),
      formValues: { organism: "PvP01", min_weight: "5000" },
      operator: "INTERSECT",
      displayName: "New name",
      colocationParams: null,
      allowedParamKeys: ALL_PARAMS,
    });
    expect(result.changeCount).toBe(4);
    expect(result.changedKeys).toContain("parameters.organism");
    expect(result.changedKeys).toContain("parameters.min_weight");
    expect(result.changedKeys).toContain("operator");
    expect(result.changedKeys).toContain("displayName");
  });

  it("ignores form keys outside allowedParamKeys", () => {
    const result = useStepDraftChanges({
      step: makeStep({ parameters: { organism: single("Pf3D7") } }),
      formValues: { organism: "Pf3D7", foo_extra: "value" },
      operator: "",
      displayName: "Step 1",
      colocationParams: null,
      allowedParamKeys: new Set(["organism"]),
    });
    expect(result.changeCount).toBe(0);
  });
});
