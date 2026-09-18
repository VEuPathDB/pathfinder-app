// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { createElement, type ReactElement } from "react";
import { render, renderHook } from "@testing-library/react";
import { useStore } from "@tanstack/react-form";
import type { ParamSpec } from "@pathfinder/shared";
import { extractDefaults, useParamForm, type ParamForm } from "./useParamForm";
import type { StepParameters } from "@/lib/types/stepParameters";

function makeSpecs(): ParamSpec[] {
  return [
    {
      name: "organism",
      type: "string",
      displayName: "Organism",
      displayType: "select",
      allowEmptyValue: false,
      isVisible: true,
      isNumber: false,
      countOnlyLeaves: false,
      initialDisplayValue: "P. falciparum 3D7",
    },
    {
      name: "min_weight",
      type: "number",
      displayName: "Min Weight",
      displayType: "",
      allowEmptyValue: true,
      isVisible: true,
      isNumber: true,
      countOnlyLeaves: false,
      initialDisplayValue: "0",
    },
  ] as ParamSpec[];
}

describe("useParamForm", () => {
  it("initializes with WDK default values", () => {
    const specs = makeSpecs();
    const { result } = renderHook(() => useParamForm(specs));
    const values = result.current.form.state.values;
    expect(values["organism"]).toBe("P. falciparum 3D7");
    expect(values["min_weight"]).toBe("0");
  });

  it("isDirty is false on mount", () => {
    const specs = makeSpecs();
    const { result } = renderHook(() => useParamForm(specs));
    expect(result.current.form.state.isDirty).toBe(false);
  });

  it("hydrated is true on mount when specs are non-empty", () => {
    const specs = makeSpecs();
    const { result } = renderHook(() => useParamForm(specs));
    expect(result.current.hydrated).toBe(true);
  });

  it("hydrated is false on mount when specs are empty", () => {
    const { result } = renderHook(() => useParamForm([]));
    expect(result.current.hydrated).toBe(false);
  });

  it("hydrated becomes true after specs arrive", () => {
    const { result, rerender } = renderHook(
      ({ specs }: { specs: ParamSpec[] }) => useParamForm(specs),
      { initialProps: { specs: [] as ParamSpec[] } },
    );
    expect(result.current.hydrated).toBe(false);
    rerender({ specs: makeSpecs() });
    expect(result.current.hydrated).toBe(true);
  });

  it("handles multi-pick defaults from JSON array string", () => {
    const specs = [
      {
        name: "go_terms",
        type: "string",
        displayName: "GO Terms",
        displayType: "checkbox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: '["GO:0006915","GO:0006916"]',
      },
    ] as ParamSpec[];
    const { result } = renderHook(() => useParamForm(specs));
    expect(result.current.form.state.values["go_terms"]).toEqual([
      "GO:0006915",
      "GO:0006916",
    ]);
  });

  it("handles multi-pick defaults from plain string", () => {
    const specs = [
      {
        name: "organisms",
        type: "string",
        displayName: "Organisms",
        displayType: "checkbox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "P. falciparum",
      },
    ] as ParamSpec[];
    const { result } = renderHook(() => useParamForm(specs));
    expect(result.current.form.state.values["organisms"]).toEqual(["P. falciparum"]);
  });

  it("handles empty multi-pick defaults", () => {
    const specs = [
      {
        name: "organisms",
        type: "string",
        displayName: "Organisms",
        displayType: "checkbox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "",
      },
    ] as ParamSpec[];
    const { result } = renderHook(() => useParamForm(specs));
    expect(result.current.form.state.values["organisms"]).toEqual([]);
  });

  it("skips hidden params in defaults", () => {
    const specs = [
      ...makeSpecs(),
      {
        name: "hidden_param",
        type: "string",
        displayName: "Hidden",
        displayType: "",
        allowEmptyValue: true,
        isVisible: false,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "secret",
      } as ParamSpec,
    ];
    const { result } = renderHook(() => useParamForm(specs));
    const values = result.current.form.state.values;
    // Only the two visible params seed defaults - the hidden one is dropped,
    // so its "secret" initial value never reaches the form.
    expect(Object.keys(values).sort()).toEqual(["min_weight", "organism"]);
    expect(values["organism"]).toBe("P. falciparum 3D7");
    expect(values["min_weight"]).toBe("0");
  });
});

describe("extractDefaults override", () => {
  it("uses override value when present (multi-pick array)", () => {
    const specs = [
      {
        name: "organism",
        type: "string",
        displayName: "Organism",
        displayType: "treeBox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "[]",
      },
    ] as ParamSpec[];
    const result = extractDefaults(specs, {
      organism: { type: "multi-pick-vocabulary", values: ["Pf3D7"] },
    });
    expect(result["organism"]).toEqual(["Pf3D7"]);
  });

  it("falls back to spec initialDisplayValue when override key missing", () => {
    const specs = [
      {
        name: "organism",
        type: "string",
        displayName: "Organism",
        displayType: "treeBox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: '["PvP01"]',
      },
    ] as ParamSpec[];
    const result = extractDefaults(specs, {
      other: { type: "string", value: "x" },
    });
    expect(result["organism"]).toEqual(["PvP01"]);
  });

  it("uses override string for single-pick param", () => {
    const specs = [
      {
        name: "name",
        type: "string",
        displayName: "Name",
        displayType: "select",
        allowEmptyValue: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "X",
      },
    ] as ParamSpec[];
    const result = extractDefaults(specs, {
      name: { type: "single-pick-vocabulary", value: "Y" },
    });
    expect(result["name"]).toBe("Y");
  });

  it("wraps a persisted single term into an array for a multi-pick param", () => {
    const specs = [
      {
        name: "organism",
        type: "string",
        displayName: "Organism",
        displayType: "checkbox",
        allowEmptyValue: true,
        allowMultipleValues: true,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "[]",
      },
    ] as ParamSpec[];
    const result = extractDefaults(specs, {
      organism: { type: "multi-pick-vocabulary", values: ["Pf3D7"] },
    });
    expect(result["organism"]).toEqual(["Pf3D7"]);
  });

  // The persisted `step.parameters` map holds TYPED ParamValue objects whose
  // shape varies by type (value / values / min+max / filters / datasetId).
  // extractDefaults must convert each via the canonical paramValueToRaw, or
  // the editor shows "[object Object]" in inputs and "0 selected" in trees.
  function specWith(over: Partial<ParamSpec> & { name: string }): ParamSpec {
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

  it("unwraps a typed StringValue to its string", () => {
    const result = extractDefaults([specWith({ name: "text_expression" })], {
      text_expression: { type: "string", value: "kinase" },
    });
    expect(result["text_expression"]).toBe("kinase");
  });

  it("unwraps a typed single-pick value to its string", () => {
    const result = extractDefaults([specWith({ name: "doc_type" })], {
      doc_type: { type: "single-pick-vocabulary", value: "gene" },
    });
    expect(result["doc_type"]).toBe("gene");
  });

  it("stringifies a typed number value", () => {
    const result = extractDefaults(
      [specWith({ name: "min_weight", type: "number", isNumber: true })],
      { min_weight: { type: "number", value: 1.3 } },
    );
    expect(result["min_weight"]).toBe("1.3");
  });

  it("uses `values` (not `value`) for a typed multi-pick value", () => {
    const result = extractDefaults(
      [
        specWith({
          name: "text_fields",
          displayType: "checkbox",
          allowMultipleValues: true,
        }),
      ],
      { text_fields: { type: "multi-pick-vocabulary", values: ["product", "gene"] } },
    );
    expect(result["text_fields"]).toEqual(["product", "gene"]);
  });

  it("encodes a typed number-range as min:max", () => {
    const result = extractDefaults(
      [specWith({ name: "dnds", type: "number-range", displayType: "" })],
      { dnds: { type: "number-range", min: 0, max: 1.3 } },
    );
    expect(result["dnds"]).toBe("0:1.3");
  });

  it("passes through a typed date value", () => {
    const result = extractDefaults([specWith({ name: "due", type: "date" })], {
      due: { type: "date", value: "2024-01-01" },
    });
    expect(result["due"]).toBe("2024-01-01");
  });

  it("serializes a typed filter value to JSON", () => {
    const filters = [{ field: "x", type: "string", value: "y" }];
    const result = extractDefaults([specWith({ name: "flt", type: "filter" })], {
      flt: { type: "filter", filters },
    });
    expect(result["flt"]).toBe(JSON.stringify(filters));
  });

  it("uses datasetId for a typed input-dataset value", () => {
    const result = extractDefaults([specWith({ name: "ds", type: "input-dataset" })], {
      ds: { type: "input-dataset", datasetId: "d-123" },
    });
    expect(result["ds"]).toBe("d-123");
  });

  it("reads a typed timestamp value", () => {
    const result = extractDefaults([specWith({ name: "seen", type: "timestamp" })], {
      seen: { type: "timestamp", value: "1717200000000" },
    });
    expect(result["seen"]).toBe("1717200000000");
  });

  it("reads a typed input-step value", () => {
    const result = extractDefaults([specWith({ name: "prior", type: "input-step" })], {
      prior: { type: "input-step", stepId: "s-42" },
    });
    expect(result["prior"]).toBe("s-42");
  });
});

describe("useParamForm - no store writes during render", () => {
  function StoreSubscriber({ form }: { form: ParamForm }): null {
    useStore(form.store, (s) => s.values);
    return null;
  }

  function Probe({ specs }: { specs: ParamSpec[] }): ReactElement {
    const { form } = useParamForm(specs);
    useStore(form.store, (s) => s.values);
    return createElement(StoreSubscriber, { form });
  }

  it("changing specs identity does not update subscribers mid-render", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(createElement(Probe, { specs: makeSpecs() }));
    rerender(createElement(Probe, { specs: makeSpecs() }));
    const offending = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("Cannot update a component"),
    );
    errorSpy.mockRestore();
    expect(offending).toEqual([]);
  });

  it("still resets values to the new defaults after a specs change", () => {
    const specsA = makeSpecs();
    const specsB = makeSpecs();
    specsB[0] = { ...specsB[0], initialDisplayValue: "P. vivax P01" } as ParamSpec;
    const { result, rerender } = renderHook(
      ({ specs }: { specs: ParamSpec[] }) => useParamForm(specs),
      { initialProps: { specs: specsA } },
    );
    expect(result.current.form.state.values["organism"]).toBe("P. falciparum 3D7");
    rerender({ specs: specsB });
    expect(result.current.form.state.values["organism"]).toBe("P. vivax P01");
  });
});

describe("useParamForm - resets when override changes", () => {
  it("resets form values when override identity changes", () => {
    const specs = [
      {
        name: "organism",
        type: "string",
        displayName: "Organism",
        displayType: "select",
        allowEmptyValue: false,
        isVisible: true,
        isNumber: false,
        countOnlyLeaves: false,
        initialDisplayValue: "default",
      },
    ] as ParamSpec[];
    const overrideA: StepParameters = {
      organism: { type: "single-pick-vocabulary", value: "A" },
    };
    const overrideB: StepParameters = {
      organism: { type: "single-pick-vocabulary", value: "B" },
    };
    const { result, rerender } = renderHook(
      ({ override }: { override: StepParameters }) => useParamForm(specs, override),
      { initialProps: { override: overrideA } },
    );
    expect(result.current.form.state.values["organism"]).toBe("A");
    rerender({ override: overrideB });
    expect(result.current.form.state.values["organism"]).toBe("B");
  });
});
