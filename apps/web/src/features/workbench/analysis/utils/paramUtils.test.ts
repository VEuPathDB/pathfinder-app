import { describe, it, expect } from "vitest";
import type { ParamSpec } from "@pathfinder/shared";
import {
  flattenVocab,
  isOptimizable,
  isParamRequired,
  isMultiPickParam,
  isParamEmpty,
  parseMultiPickInitial,
  resolveDisplayValue,
  isNumericParam,
  buildDisplayMap,
} from "./paramUtils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSpec(
  overrides: Partial<ParamSpec> & { name: string; type: string } & Record<
      string,
      unknown
    >,
): ParamSpec {
  return { ...overrides };
}

// ---------------------------------------------------------------------------
// flattenVocab
// ---------------------------------------------------------------------------

describe("flattenVocab", () => {
  it("flattens a simple string array", () => {
    const result = flattenVocab(["a", "b", "c"]);
    expect(result).toEqual([
      { value: "a", display: "a" },
      { value: "b", display: "b" },
      { value: "c", display: "c" },
    ]);
  });

  it("flattens array of [value, label] tuples", () => {
    const result = flattenVocab([
      ["v1", "Label 1"],
      ["v2", "Label 2"],
    ]);
    expect(result).toEqual([
      { value: "v1", display: "Label 1" },
      { value: "v2", display: "Label 2" },
    ]);
  });

  it("flattens array of objects with value/display keys", () => {
    const result = flattenVocab([
      { value: "x", display: "X Display" },
      { value: "y", display: "Y Display" },
    ]);
    expect(result).toEqual([
      { value: "x", display: "X Display" },
      { value: "y", display: "Y Display" },
    ]);
  });

  it("returns empty array for null/undefined", () => {
    expect(flattenVocab(null)).toEqual([]);
    expect(flattenVocab(undefined)).toEqual([]);
  });

  it("returns empty array for empty array", () => {
    expect(flattenVocab([])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// isOptimizable
// ---------------------------------------------------------------------------

describe("isOptimizable", () => {
  it("returns false for input-step", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "input-step" }))).toBe(false);
  });

  it("returns false for input-dataset", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "input-dataset" }))).toBe(false);
  });

  it("returns false for filter", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "filter" }))).toBe(false);
  });

  it("returns true for string type", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "string" }))).toBe(true);
  });

  it("returns true for number type", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "number" }))).toBe(true);
  });

  it("returns true for multi-pick-vocabulary type", () => {
    expect(isOptimizable(makeSpec({ name: "a", type: "multi-pick-vocabulary" }))).toBe(
      true,
    );
  });
});

// ---------------------------------------------------------------------------
// isParamRequired
// ---------------------------------------------------------------------------

describe("isParamRequired", () => {
  it("returns true for a basic visible param", () => {
    expect(isParamRequired(makeSpec({ name: "a", type: "string" }))).toBe(true);
  });

  it("returns false when allowEmptyValue is true", () => {
    expect(
      isParamRequired(makeSpec({ name: "a", type: "string", allowEmptyValue: true })),
    ).toBe(false);
  });

  it("returns false when isReadOnly is true", () => {
    expect(
      isParamRequired(makeSpec({ name: "a", type: "string", isReadOnly: true })),
    ).toBe(false);
  });

  it("returns false when isVisible is false", () => {
    expect(
      isParamRequired(makeSpec({ name: "a", type: "string", isVisible: false })),
    ).toBe(false);
  });

  it("returns false for input-step type", () => {
    expect(isParamRequired(makeSpec({ name: "a", type: "input-step" }))).toBe(false);
  });

  it("returns true when isVisible is true", () => {
    expect(
      isParamRequired(makeSpec({ name: "a", type: "string", isVisible: true })),
    ).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// isMultiPickParam
// ---------------------------------------------------------------------------

describe("isMultiPickParam", () => {
  it("returns true for multi-pick-vocabulary type", () => {
    expect(
      isMultiPickParam(makeSpec({ name: "a", type: "multi-pick-vocabulary" })),
    ).toBe(true);
  });

  it("returns true when multiPick is true", () => {
    expect(
      isMultiPickParam(makeSpec({ name: "a", type: "string", multiPick: true })),
    ).toBe(true);
  });

  it("returns false for single-pick type without multiPick flag", () => {
    expect(isMultiPickParam(makeSpec({ name: "a", type: "string" }))).toBe(false);
  });

  it("returns false when multiPick is false", () => {
    expect(
      isMultiPickParam(makeSpec({ name: "a", type: "string", multiPick: false })),
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isParamEmpty
// ---------------------------------------------------------------------------

describe("isParamEmpty", () => {
  it("returns true for empty string", () => {
    expect(isParamEmpty(makeSpec({ name: "a", type: "string" }), "")).toBe(true);
  });

  it("returns false for non-empty string", () => {
    expect(isParamEmpty(makeSpec({ name: "a", type: "string" }), "hello")).toBe(false);
  });

  it("returns true for '[]' when multiPick", () => {
    expect(
      isParamEmpty(makeSpec({ name: "a", type: "multi-pick-vocabulary" }), "[]"),
    ).toBe(true);
  });

  it("returns false for '[]' on non-multiPick param", () => {
    expect(isParamEmpty(makeSpec({ name: "a", type: "string" }), "[]")).toBe(false);
  });

  it("returns false for non-empty multiPick value", () => {
    expect(
      isParamEmpty(makeSpec({ name: "a", type: "multi-pick-vocabulary" }), '["a","b"]'),
    ).toBe(false);
  });

  it("returns true when value is null-ish (cast to string check)", () => {
    // The function checks value == null first
    expect(isParamEmpty(makeSpec({ name: "a", type: "string" }), null)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// parseMultiPickInitial
// ---------------------------------------------------------------------------

describe("parseMultiPickInitial", () => {
  it("parses a JSON array into comma-separated string for multiPick param", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    expect(parseMultiPickInitial(spec, '["x","y","z"]')).toBe("x,y,z");
  });

  it("returns raw value for non-multiPick param", () => {
    const spec = makeSpec({ name: "a", type: "string" });
    expect(parseMultiPickInitial(spec, '["x","y"]')).toBe('["x","y"]');
  });

  it("returns raw value when input is not JSON array format", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    expect(parseMultiPickInitial(spec, "plain text")).toBe("plain text");
  });

  it("returns raw value when JSON is invalid", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    expect(parseMultiPickInitial(spec, "[invalid json")).toBe("[invalid json");
  });

  it("returns raw value when parsed JSON is not an array", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    // '{"a":1}' starts with '{' not '[', so it returns raw
    expect(parseMultiPickInitial(spec, '{"a":1}')).toBe('{"a":1}');
  });

  it("handles empty JSON array", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    expect(parseMultiPickInitial(spec, "[]")).toBe("");
  });

  it("handles single-element array", () => {
    const spec = makeSpec({ name: "a", type: "multi-pick-vocabulary" });
    expect(parseMultiPickInitial(spec, '["only"]')).toBe("only");
  });
});

// ---------------------------------------------------------------------------
// resolveDisplayValue
// ---------------------------------------------------------------------------

describe("resolveDisplayValue", () => {
  it("resolves value to display label when vocab has a match", () => {
    const spec = makeSpec({
      name: "a",
      type: "string",
      vocabulary: [
        ["v1", "Display One", null],
        ["v2", "Display Two", null],
      ],
    });
    expect(resolveDisplayValue("v1", spec)).toBe("Display One");
  });

  it("returns the raw value when no match found", () => {
    const spec = makeSpec({
      name: "a",
      type: "string",
      vocabulary: [["v1", "Display One", null]],
    });
    expect(resolveDisplayValue("unknown", spec)).toBe("unknown");
  });

  it("returns the raw value when spec is null", () => {
    expect(resolveDisplayValue("hello", null)).toBe("hello");
  });

  it("returns the raw value when spec is undefined", () => {
    expect(resolveDisplayValue("hello", undefined)).toBe("hello");
  });

  it("returns the raw value when spec has no vocabulary", () => {
    const spec = makeSpec({ name: "a", type: "string" });
    expect(resolveDisplayValue("hello", spec)).toBe("hello");
  });
});

// ---------------------------------------------------------------------------
// isNumericParam
// ---------------------------------------------------------------------------

describe("isNumericParam", () => {
  it("returns true for type 'number'", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "number" }))).toBe(true);
  });

  it("returns true for type 'number-range'", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "number-range" }))).toBe(true);
  });

  it("returns true for type 'integer'", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "integer" }))).toBe(true);
  });

  it("returns true for type 'float'", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "float" }))).toBe(true);
  });

  it("returns true when isNumber flag is set", () => {
    expect(
      isNumericParam(makeSpec({ name: "a", type: "string", isNumber: true })),
    ).toBe(true);
  });

  it("returns false for plain string type", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "string" }))).toBe(false);
  });

  it("is case-insensitive on type", () => {
    expect(isNumericParam(makeSpec({ name: "a", type: "NUMBER" }))).toBe(true);
    expect(isNumericParam(makeSpec({ name: "a", type: "Integer" }))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// buildDisplayMap
// ---------------------------------------------------------------------------

describe("buildDisplayMap", () => {
  it("maps parameter values to display labels", () => {
    const parameters = { organism: "pf3d7" };
    const paramSpecs: ParamSpec[] = [
      makeSpec({
        name: "organism",
        type: "string",
        vocabulary: [
          ["pf3d7", "P. falciparum 3D7", null],
          ["pvsal", "P. vivax Sal-I", null],
        ],
      }),
    ];
    const result = buildDisplayMap(parameters, paramSpecs);
    expect(result).toEqual({ organism: "P. falciparum 3D7" });
  });

  it("skips params without vocabulary", () => {
    const parameters = { text: "hello" };
    const paramSpecs: ParamSpec[] = [makeSpec({ name: "text", type: "string" })];
    const result = buildDisplayMap(parameters, paramSpecs);
    expect(result).toEqual({});
  });

  it("skips when display equals value (no mapping needed)", () => {
    const parameters = { org: "alpha" };
    const paramSpecs: ParamSpec[] = [
      makeSpec({
        name: "org",
        type: "string",
        vocabulary: [
          ["alpha", "alpha", null],
          ["beta", "beta", null],
        ],
      }),
    ];
    const result = buildDisplayMap(parameters, paramSpecs);
    // display === value ("alpha" === "alpha"), so no entry
    expect(result).toEqual({});
  });

  it("handles multi-pick params by joining display values", () => {
    const parameters = { orgs: "v1,v2" };
    const paramSpecs: ParamSpec[] = [
      makeSpec({
        name: "orgs",
        type: "multi-pick-vocabulary",
        vocabulary: [
          ["v1", "Label One", null],
          ["v2", "Label Two", null],
        ],
      }),
    ];
    const result = buildDisplayMap(parameters, paramSpecs);
    expect(result).toEqual({ orgs: "Label One, Label Two" });
  });

  it("handles missing spec for a parameter key", () => {
    const parameters = { unknown: "value" };
    const paramSpecs: ParamSpec[] = [];
    const result = buildDisplayMap(parameters, paramSpecs);
    expect(result).toEqual({});
  });

  it("handles empty parameters", () => {
    const result = buildDisplayMap({}, []);
    expect(result).toEqual({});
  });

  it("falls back to raw value for unmatched multi-pick entries", () => {
    const parameters = { orgs: "v1,unknown" };
    const paramSpecs: ParamSpec[] = [
      makeSpec({
        name: "orgs",
        type: "multi-pick-vocabulary",
        vocabulary: [["v1", "Label One", null]],
      }),
    ];
    const result = buildDisplayMap(parameters, paramSpecs);
    expect(result).toEqual({ orgs: "Label One, unknown" });
  });
});
