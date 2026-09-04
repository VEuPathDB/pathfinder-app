import { describe, expect, it } from "vitest";
import type { ValidationResult, ValidationResponse } from "@pathfinder/shared";
import { formatSearchValidationResponse } from "./format";

// ---------------------------------------------------------------------------
// Helpers to build valid test data without `as any`
// ---------------------------------------------------------------------------

function makePayload(overrides: Partial<ValidationResult>): ValidationResult {
  return {
    isValid: true,
    normalizedContextValues: {},
    errors: { general: [], byKey: {} },
    ...overrides,
  };
}

function makeResponse(payload: ValidationResult): ValidationResponse {
  return { validation: payload };
}

// ---------------------------------------------------------------------------
// formatSearchValidationResponse
// ---------------------------------------------------------------------------
describe("formatSearchValidationResponse", () => {
  // ----- null / undefined / valid responses -----
  describe("returns null message for non-error responses", () => {
    it("returns null for null input", () => {
      const result = formatSearchValidationResponse(null);
      expect(result).toEqual({ message: null, keys: new Set() });
    });

    it("returns null for undefined input", () => {
      const result = formatSearchValidationResponse(undefined);
      expect(result).toEqual({ message: null, keys: new Set() });
    });

    it("returns null when isValid is true", () => {
      const response = makeResponse(makePayload({ isValid: true }));
      const result = formatSearchValidationResponse(response);
      expect(result).toEqual({ message: null, keys: new Set() });
    });

    it("returns null when validation payload is undefined", () => {
      // Simulate a response where the `validation` field is missing entirely.
      const response = { validation: undefined } as unknown as ValidationResponse;
      const result = formatSearchValidationResponse(response);
      expect(result).toEqual({ message: null, keys: new Set() });
    });
  });

  // ----- general errors -----
  describe("general errors", () => {
    it("includes general errors in message", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: { general: ["Something went wrong"], byKey: {} },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe("Cannot be saved: Something went wrong");
      expect(result.keys.size).toBe(0);
    });

    it("joins multiple general errors with semicolons", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: { general: ["Error A", "Error B"], byKey: {} },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe("Cannot be saved: Error A; Error B");
    });
  });

  // ----- byKey errors -----
  describe("byKey errors", () => {
    it("includes keyed errors and populates keys set", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: [],
            byKey: { organism: ["Must select at least one"] },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe(
        "Cannot be saved: organism: Must select at least one",
      );
      expect(result.keys).toEqual(new Set(["organism"]));
    });

    it("joins multiple messages per key with commas", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: [],
            byKey: { threshold: ["Too low", "Must be positive"] },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe(
        "Cannot be saved: threshold: Too low, Must be positive",
      );
      expect(result.keys).toEqual(new Set(["threshold"]));
    });

    it("skips keys with empty message arrays", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: [],
            byKey: { empty: [], hasError: ["Bad value"] },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe("Cannot be saved: hasError: Bad value");
      expect(result.keys).toEqual(new Set(["hasError"]));
      expect(result.keys.has("empty")).toBe(false);
    });

    it("skips keys with undefined message arrays", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: [],
            byKey: {
              broken: undefined as unknown as string[],
              valid: ["ok"],
            },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.keys).toEqual(new Set(["valid"]));
    });
  });

  // ----- combined general + byKey -----
  describe("combined general and byKey errors", () => {
    it("joins general and byKey errors with semicolons", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: ["Global issue"],
            byKey: { param1: ["Invalid value"] },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe(
        "Cannot be saved: Global issue; param1: Invalid value",
      );
      expect(result.keys).toEqual(new Set(["param1"]));
    });

    it("handles multiple byKey entries", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: {
            general: [],
            byKey: {
              alpha: ["err1"],
              beta: ["err2", "err3"],
            },
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toContain("alpha: err1");
      expect(result.message).toContain("beta: err2, err3");
      expect(result.keys).toEqual(new Set(["alpha", "beta"]));
    });
  });

  // ----- fallback message -----
  describe("fallback when isValid is false but no error details", () => {
    it("uses generic fallback when both general and byKey are empty", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: { general: [], byKey: {} },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe("Cannot be saved: parameters do not match the spec.");
      expect(result.keys.size).toBe(0);
    });

    it("uses generic fallback when errors field is missing", () => {
      const response = makeResponse(
        makePayload({
          isValid: false,
          errors: undefined as unknown as {
            general: string[];
            byKey: Record<string, string[]>;
          },
        }),
      );
      const result = formatSearchValidationResponse(response);
      expect(result.message).toBe("Cannot be saved: parameters do not match the spec.");
    });
  });
});
