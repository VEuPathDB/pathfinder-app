import { describe, it, expect } from "vitest";
import { isMultiParam } from "./spec";
import type { ParamSpec } from "./spec";

describe("isMultiParam", () => {
  describe("allowMultipleValues flag", () => {
    it("returns true when allowMultipleValues is true", () => {
      expect(isMultiParam({ allowMultipleValues: true })).toBe(true);
    });

    it("returns false when allowMultipleValues is false and no other multi signals", () => {
      expect(isMultiParam({ allowMultipleValues: false })).toBe(false);
    });
  });

  describe("multiPick flag", () => {
    it("returns true when multiPick is true", () => {
      expect(isMultiParam({ multiPick: true })).toBe(true);
    });

    it("returns false when multiPick is false", () => {
      expect(isMultiParam({ multiPick: false })).toBe(false);
    });
  });

  describe("maxSelectedCount", () => {
    it("returns true when maxSelectedCount > 1", () => {
      expect(isMultiParam({ maxSelectedCount: 5 })).toBe(true);
    });

    it("returns false when maxSelectedCount is 1", () => {
      expect(isMultiParam({ maxSelectedCount: 1 })).toBe(false);
    });

    it("returns false when maxSelectedCount is 0", () => {
      expect(isMultiParam({ maxSelectedCount: 0 })).toBe(false);
    });

    it("returns false when maxSelectedCount is undefined", () => {
      expect(isMultiParam({})).toBe(false);
    });
  });

  describe("type string heuristic", () => {
    it("returns true when type contains 'multi' (case-insensitive)", () => {
      expect(isMultiParam({ type: "multi-pick" })).toBe(true);
      expect(isMultiParam({ type: "MultiPickList" })).toBe(true);
      expect(isMultiParam({ type: "MULTI_SELECT" })).toBe(true);
    });

    it("returns false for types that do not contain 'multi'", () => {
      expect(isMultiParam({ type: "string" })).toBe(false);
      expect(isMultiParam({ type: "number" })).toBe(false);
      expect(isMultiParam({ type: "single-pick" })).toBe(false);
      expect(isMultiParam({ type: "tree-box" })).toBe(false);
    });

    it("returns false when type is undefined", () => {
      expect(isMultiParam({})).toBe(false);
    });

    it("returns false for empty string type", () => {
      expect(isMultiParam({ type: "" })).toBe(false);
    });
  });

  describe("precedence: early flags short-circuit before type check", () => {
    it("returns true via allowMultipleValues even if type is 'string'", () => {
      expect(isMultiParam({ allowMultipleValues: true, type: "string" })).toBe(true);
    });

    it("returns true via multiPick even if maxSelectedCount is 1", () => {
      expect(isMultiParam({ multiPick: true, maxSelectedCount: 1 })).toBe(true);
    });
  });

  describe("ParamSpec with extra fields", () => {
    it("handles a fully-populated ParamSpec correctly", () => {
      const spec: ParamSpec = {
        name: "organism",
        displayName: "Organism",
        help: "Select organisms",
        type: "multi-pick",
        allowEmptyValue: false,
        allowMultipleValues: true,
        multiPick: true,
        vocabulary: [
          ["a", "a", null],
          ["b", "b", null],
        ],
        maxSelectedCount: 10,
        minSelectedCount: 1,
        countOnlyLeaves: false,
        isNumber: false,
        isVisible: true,
      };
      expect(isMultiParam(spec)).toBe(true);
    });

    it("returns false for a plain scalar spec", () => {
      const spec: ParamSpec = {
        name: "min_length",
        displayName: "Min Length",
        type: "number",
        allowEmptyValue: false,
        countOnlyLeaves: false,
        isNumber: true,
        isVisible: true,
      };
      expect(isMultiParam(spec)).toBe(false);
    });
  });
});
