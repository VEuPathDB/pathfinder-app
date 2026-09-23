import { describe, expect, it } from "vitest";
import type { ParamSpec, Step } from "@pathfinder/shared";
import { updateStepParamsOpSchema } from "@pathfinder/shared/generated/zod/updateStepParamsOpSchema";
import { extractDefaults } from "./hooks/useParamForm";
import { buildStepPatch } from "./buildStepPatch";
import type { ParamValueMap } from "@/lib/parameters/paramValue";

function spec(over: Partial<ParamSpec> & { name: string }): ParamSpec {
  return {
    type: "string",
    displayName: over.name,
    displayType: "",
    allowEmptyValue: true,
    isVisible: true,
    isNumber: false,
    countOnlyLeaves: false,
    initialDisplayValue: "",
    ...over,
  };
}

const SPECS: ParamSpec[] = [
  spec({
    name: "organism",
    type: "multi-pick-vocabulary",
    displayType: "treeBox",
    allowMultipleValues: true,
  }),
  spec({ name: "min_weight", type: "number", isNumber: true }),
  spec({ name: "dnds", type: "number-range" }),
];

const PERSISTED: ParamValueMap = {
  organism: { type: "multi-pick-vocabulary", values: ["Pf3D7"] },
  min_weight: { type: "number", value: 5 },
  dnds: { type: "number-range", min: 0, max: 1.3 },
};

function stepWith(parameters: ParamValueMap): Step {
  return { id: "step-1", searchName: "GenesByTaxon", parameters };
}

function patchFor(formValues: Record<string, string | string[]>) {
  return buildStepPatch({
    step: stepWith(PERSISTED),
    formValues,
    hiddenDefaults: {},
    allowedParamKeys: new Set(SPECS.map((s) => s.name)),
    paramSpecs: SPECS,
    operator: "",
    displayName: "",
    colocationParams: null,
  });
}

describe("parameter round trip through the editor", () => {
  it("shows each persisted value as the raw value its widget reads", () => {
    const defaults = extractDefaults(SPECS, PERSISTED);
    expect(defaults["organism"]).toEqual(["Pf3D7"]);
    expect(defaults["min_weight"]).toBe("5");
    expect(defaults["dnds"]).toBe("0:1.3");
  });

  it("sends back the typed value the wire accepts after an edit", () => {
    const defaults = extractDefaults(SPECS, PERSISTED);
    const patch = patchFor({ ...defaults, organism: ["Pf3D7", "PvP01"] });

    expect(patch.parameters).toEqual({
      organism: { type: "multi-pick-vocabulary", values: ["Pf3D7", "PvP01"] },
    });
    const parsed = updateStepParamsOpSchema.parse({
      kind: "updateStepParams",
      stepId: "step-1",
      parameters: patch.parameters,
    });
    expect(parsed.parameters["organism"]).toEqual({
      type: "multi-pick-vocabulary",
      values: ["Pf3D7", "PvP01"],
    });
  });

  it("sends a number back as a number and a range back as its endpoints", () => {
    const defaults = extractDefaults(SPECS, PERSISTED);
    const patch = patchFor({ ...defaults, min_weight: "7", dnds: "0.5:2" });

    expect(patch.parameters).toEqual({
      min_weight: { type: "number", value: 7 },
      dnds: { type: "number-range", min: 0.5, max: 2 },
    });
  });

  it("reports no change when nothing is edited", () => {
    const defaults = extractDefaults(SPECS, PERSISTED);
    const patch = patchFor(defaults);
    expect(Object.keys(patch)).toEqual([]);
  });
});

describe("a transform step's input wiring", () => {
  const ORTHOLOG_SPECS: ParamSpec[] = [
    spec({
      name: "gene_result",
      type: "input-step",
      isVisible: false,
      group: "_hidden",
      initialDisplayValue: "",
    }),
    spec({
      name: "isSyntenic",
      type: "single-pick-vocabulary",
      displayType: "select",
      allowEmptyValue: false,
      initialDisplayValue: "no",
    }),
  ];

  it("sends only the edited parameter and never the input step", () => {
    const patch = buildStepPatch({
      step: {
        id: "step-2",
        searchName: "GenesByOrthologs",
        parameters: { isSyntenic: { type: "single-pick-vocabulary", value: "no" } },
      },
      formValues: { isSyntenic: "yes" },
      hiddenDefaults: { gene_result: "" },
      allowedParamKeys: new Set(["isSyntenic"]),
      paramSpecs: ORTHOLOG_SPECS,
      operator: "",
      displayName: "",
      colocationParams: null,
    });

    expect(patch.parameters).toEqual({
      isSyntenic: { type: "single-pick-vocabulary", value: "yes" },
    });
    const parsed = updateStepParamsOpSchema.safeParse({
      kind: "updateStepParams",
      stepId: "step-2",
      parameters: patch.parameters,
    });
    expect(parsed.success).toBe(true);
  });
});
