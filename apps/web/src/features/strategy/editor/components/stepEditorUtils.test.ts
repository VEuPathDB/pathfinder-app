import { describe, it, expect } from "vitest";
import { extractSpecVocabulary } from "./stepEditorUtils";
import { buildContextValues } from "@/lib/utils/buildContextValues";

// ---------------------------------------------------------------------------
// extractSpecVocabulary
// ---------------------------------------------------------------------------
describe("extractSpecVocabulary", () => {
  it("returns vocabulary when present", () => {
    expect(extractSpecVocabulary({ vocabulary: ["a", "b"] })).toEqual(["a", "b"]);
  });

  it("returns undefined when vocabulary is absent", () => {
    expect(extractSpecVocabulary({})).toEqual(undefined);
  });

  it("returns undefined when vocabulary is null", () => {
    expect(extractSpecVocabulary({ vocabulary: null })).toEqual(undefined);
  });

  it("returns empty array vocabulary as-is", () => {
    expect(extractSpecVocabulary({ vocabulary: [] })).toEqual([]);
  });

  it("returns object vocabulary as-is", () => {
    const vocab = { terms: [["a", "Alpha"]], treeNodes: [] };
    expect(extractSpecVocabulary({ vocabulary: vocab })).toEqual(vocab);
  });
});

// ---------------------------------------------------------------------------
// buildContextValues
// ---------------------------------------------------------------------------
describe("buildContextValues", () => {
  describe("filtering out sentinel and empty values", () => {
    it("excludes a single-pick value that carries the All sentinel", () => {
      const result = buildContextValues({
        a: { type: "single-pick-vocabulary", value: "@@fake@@" },
        b: { type: "single-pick-vocabulary", value: "Pf3D7" },
      });
      expect(result).toEqual({
        b: { type: "single-pick-vocabulary", value: "Pf3D7" },
      });
    });

    it("excludes a multi-pick value that carries the All sentinel", () => {
      const result = buildContextValues({
        a: { type: "multi-pick-vocabulary", values: ["@@fake@@"] },
        b: { type: "multi-pick-vocabulary", values: ["x", "y"] },
      });
      expect(result).toEqual({
        b: { type: "multi-pick-vocabulary", values: ["x", "y"] },
      });
    });

    it("excludes a multi-pick value with the All sentinel among real terms", () => {
      const result = buildContextValues({
        a: { type: "multi-pick-vocabulary", values: ["ok", "@@fake@@"] },
      });
      expect(result).toEqual({});
    });

    it("excludes an empty string value", () => {
      const result = buildContextValues({
        a: { type: "string", value: "" },
        b: { type: "string", value: "ok" },
      });
      expect(result).toEqual({ b: { type: "string", value: "ok" } });
    });

    it("excludes an empty multi-pick value", () => {
      const result = buildContextValues({
        a: { type: "multi-pick-vocabulary", values: [] },
        b: { type: "multi-pick-vocabulary", values: ["PvP01"] },
      });
      expect(result).toEqual({
        b: { type: "multi-pick-vocabulary", values: ["PvP01"] },
      });
    });

    it("excludes a range value with neither endpoint", () => {
      const result = buildContextValues({
        a: { type: "number-range", min: null, max: null },
        b: { type: "number-range", min: 0, max: null },
      });
      expect(result).toEqual({ b: { type: "number-range", min: 0, max: null } });
    });

    it("excludes a filter value with no clauses", () => {
      const result = buildContextValues({
        a: { type: "filter", filters: [] },
      });
      expect(result).toEqual({});
    });
  });

  describe("retaining valid values", () => {
    it("keeps a non-empty string value", () => {
      const result = buildContextValues({ name: { type: "string", value: "hello" } });
      expect(result).toEqual({ name: { type: "string", value: "hello" } });
    });

    it("keeps a zero number value", () => {
      const result = buildContextValues({
        count: { type: "number", value: 0 },
        size: { type: "number", value: 10 },
      });
      expect(result).toEqual({
        count: { type: "number", value: 0 },
        size: { type: "number", value: 10 },
      });
    });

    it("keeps an input-step value", () => {
      const result = buildContextValues({
        prior: { type: "input-step", stepId: "s-1" },
      });
      expect(result).toEqual({ prior: { type: "input-step", stepId: "s-1" } });
    });
  });

  describe("allowedKeys filtering", () => {
    it("only includes keys in the allowedKeys list", () => {
      const result = buildContextValues(
        {
          a: { type: "string", value: "yes" },
          b: { type: "string", value: "no" },
          c: { type: "string", value: "maybe" },
        },
        ["a", "c"],
      );
      expect(result).toEqual({
        a: { type: "string", value: "yes" },
        c: { type: "string", value: "maybe" },
      });
    });

    it("still filters out the All sentinel when the key is allowed", () => {
      const result = buildContextValues(
        {
          a: { type: "single-pick-vocabulary", value: "@@fake@@" },
          b: { type: "single-pick-vocabulary", value: "real" },
        },
        ["a", "b"],
      );
      expect(result).toEqual({
        b: { type: "single-pick-vocabulary", value: "real" },
      });
    });

    it("returns empty when no keys match", () => {
      const result = buildContextValues({ a: { type: "string", value: "val" } }, [
        "b",
        "c",
      ]);
      expect(result).toEqual({});
    });

    it("includes all valid values when allowedKeys is undefined", () => {
      const result = buildContextValues({
        a: { type: "string", value: "x" },
        b: { type: "string", value: "y" },
      });
      expect(result).toEqual({
        a: { type: "string", value: "x" },
        b: { type: "string", value: "y" },
      });
    });

    it("handles empty allowedKeys array (nothing passes)", () => {
      const result = buildContextValues({ a: { type: "string", value: "x" } }, []);
      expect(result).toEqual({});
    });
  });

  describe("combined edge cases", () => {
    it("handles all-filtered-out input", () => {
      const result = buildContextValues({
        a: { type: "string", value: "" },
        b: { type: "multi-pick-vocabulary", values: [] },
        c: { type: "date-range", min: null, max: null },
        d: { type: "single-pick-vocabulary", value: "@@fake@@" },
        e: { type: "multi-pick-vocabulary", values: ["@@fake@@"] },
      });
      expect(result).toEqual({});
    });

    it("handles empty input", () => {
      expect(buildContextValues({})).toEqual({});
    });
  });
});
