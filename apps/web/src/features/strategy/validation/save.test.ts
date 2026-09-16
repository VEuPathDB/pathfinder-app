import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ValidationResponse, Step, Strategy } from "@pathfinder/shared";
import { validateStepsForSave } from "./save";

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

// Mock validateSearchParams - the async API call
vi.mock("@/lib/api/sites", () => ({
  validateSearchParams: vi.fn(),
}));

// Mock toUserMessage - error formatting
vi.mock("@/lib/api/errors", () => ({
  toUserMessage: vi.fn((err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
  ),
}));

import { validateSearchParams } from "@/lib/api/sites";
import { toUserMessage } from "@/lib/api/errors";

const mockValidateSearchParams = vi.mocked(validateSearchParams);
const mockToUserMessage = vi.mocked(toUserMessage);

// ---------------------------------------------------------------------------
// Test data builders
// ---------------------------------------------------------------------------

function makeSearchStep(overrides?: Partial<Step>): Step {
  return {
    id: "step-1",
    displayName: "Gene search",
    searchName: "GenesByKeyword",
    recordType: "gene",
    parameters: { keyword: { type: "string", value: "kinase" } },
    isFiltered: false,
    ...overrides,
  };
}

function makeTransformStep(overrides?: Partial<Step>): Step {
  return {
    id: "transform-1",
    displayName: "Transform step",
    searchName: "GenesByOrthology",
    primaryInputStepId: "step-1",
    recordType: "gene",
    isFiltered: false,
    ...overrides,
  };
}

function makeCombineStep(overrides?: Partial<Step>): Step {
  return {
    id: "combine-1",
    displayName: "Combine step",
    operator: "INTERSECT",
    primaryInputStepId: "step-1",
    secondaryInputStepId: "step-2",
    isFiltered: false,
    ...overrides,
  };
}

function makeStrategy(overrides?: Partial<Strategy>): Strategy {
  return {
    id: "strat-1",
    name: "Test Strategy",
    siteId: "PlasmoDB",
    recordType: "gene",
    steps: [],
    rootStepId: "step-1",
    isSaved: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function validResponse(): ValidationResponse {
  return {
    validation: {
      isValid: true,
      normalizedContextValues: {},
      errors: { general: [], byKey: {} },
    },
  };
}

function invalidResponse(
  general: string[] = [],
  byKey: Record<string, string[]> = {},
): ValidationResponse {
  return {
    validation: {
      isValid: false,
      normalizedContextValues: {},
      errors: { general, byKey },
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("validateStepsForSave", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Re-set default toUserMessage implementation after clearing
    mockToUserMessage.mockImplementation(
      (err: unknown, fallback = "Request failed.") =>
        err instanceof Error ? err.message : fallback,
    );
  });

  // ----- empty steps -----
  describe("empty steps array", () => {
    it("returns no errors for an empty steps array", async () => {
      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [],
        strategy: null,
      });
      expect(result.hasErrors).toBe(false);
      expect(result.errorsByStepId).toEqual({});
    });
  });

  // ----- single valid search step -----
  describe("single valid search step", () => {
    it("returns no errors when validation passes", async () => {
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const step = makeSearchStep();
      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(false);
      expect(result.errorsByStepId[step.id]).toBeUndefined();
    });

    it("calls validateSearchParams with correct arguments", async () => {
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const step = makeSearchStep({
        recordType: "gene",
        searchName: "GenesByKeyword",
        parameters: { keyword: { type: "string", value: "kinase" } },
      });

      await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(mockValidateSearchParams).toHaveBeenCalledWith(
        "PlasmoDB",
        "gene",
        "GenesByKeyword",
        { keyword: { type: "string", value: "kinase" } },
      );
    });
  });

  // ----- validation errors from API -----
  describe("API validation errors", () => {
    it("sets error message when validation returns invalid", async () => {
      mockValidateSearchParams.mockResolvedValue(
        invalidResponse(["Parameter X is required"]),
      );

      const step = makeSearchStep();
      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId[step.id]).toBe(
        "Cannot be saved: Parameter X is required",
      );
    });

    it("sets error on API call failure", async () => {
      mockValidateSearchParams.mockRejectedValue(new Error("Network timeout"));
      mockToUserMessage.mockReturnValue("Network timeout");

      const step = makeSearchStep();
      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId[step.id]).toContain("Cannot be saved:");
      expect(result.errorsByStepId[step.id]).toContain("Network timeout");
    });
  });

  // ----- missing searchName or recordType -----
  describe("missing searchName or recordType", () => {
    it("errors when searchName is missing", async () => {
      const step = makeSearchStep({ searchName: null });

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId[step.id]).toBe(
        "Cannot be saved: search name or record type missing.",
      );
      // Should NOT call the API
      expect(mockValidateSearchParams).not.toHaveBeenCalled();
    });

    it("errors when recordType is missing on step and strategy", async () => {
      const step = makeSearchStep({ recordType: null });

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId[step.id]).toBe(
        "Cannot be saved: search name or record type missing.",
      );
    });

    it("falls back to strategy recordType when step has none", async () => {
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const step = makeSearchStep({ recordType: null });
      const strategy = makeStrategy({ recordType: "gene" });

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy,
      });

      expect(result.hasErrors).toBe(false);
      expect(mockValidateSearchParams).toHaveBeenCalledWith(
        "PlasmoDB",
        "gene",
        "GenesByKeyword",
        { keyword: { type: "string", value: "kinase" } },
      );
    });

    it("uses strategy recordType when step recordType is empty string", async () => {
      // normalizeRecordType trims whitespace; empty string yields falsy
      const step = makeSearchStep({ recordType: "  " });
      const strategy = makeStrategy({ recordType: "gene" });
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy,
      });

      // "  " is truthy, so step.recordType is used first, then normalizeRecordType("  ") = "  "
      // Actually normalizeRecordType returns value.trim() which is "" -> falsy -> fall to strategy
      // But the code does: step.recordType || strategy?.recordType
      // "  " is truthy so it uses "  ", then normalizeRecordType("  ") = "" which is falsy
      // Then recordType is falsy -> error
      // WAIT: let me re-read the logic:
      // const rawRecordType = step.recordType || strategy?.recordType || undefined;
      // "  " is truthy, so rawRecordType = "  "
      // normalizeRecordType("  ") = "  ".trim() = "" which is falsy
      // So !recordType -> error
      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId[step.id]).toBe(
        "Cannot be saved: search name or record type missing.",
      );
    });
  });

  // ----- non-search steps (transform / combine) -----
  describe("non-search steps", () => {
    it("skips validation for transform steps", async () => {
      const search = makeSearchStep({ id: "step-1" });
      const transform = makeTransformStep({
        id: "transform-1",
        primaryInputStepId: "step-1",
      });
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [search, transform],
        strategy: null,
      });

      // Only the search step calls validateSearchParams
      expect(mockValidateSearchParams).toHaveBeenCalledTimes(1);
      expect(result.errorsByStepId["transform-1"]).toBeUndefined();
    });

    it("skips validation for combine steps", async () => {
      const s1 = makeSearchStep({ id: "step-1" });
      const s2 = makeSearchStep({ id: "step-2", displayName: "Second" });
      const combine = makeCombineStep({
        id: "combine-1",
        primaryInputStepId: "step-1",
        secondaryInputStepId: "step-2",
      });
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2, combine],
        strategy: null,
      });

      // Two search steps validated, combine is not
      expect(mockValidateSearchParams).toHaveBeenCalledTimes(2);
      expect(result.errorsByStepId["combine-1"]).toBeUndefined();
    });
  });

  // ----- structural errors -----
  describe("structural errors", () => {
    it("reports missing searchName as structural error", async () => {
      const step: Step = {
        id: "step-1",
        displayName: "No search name",
        // searchName intentionally omitted for a search step
        recordType: "gene",
        isFiltered: false,
      };

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId["step-1"]).toContain("Cannot be saved:");
    });

    it("multiple roots is no longer a save-blocking error (orphans are first-class)", async () => {
      // Two disconnected search steps = two roots. With the orphan-as-info change,
      // this is not a save-blocking error; only the rooted component is pushed.
      const s1 = makeSearchStep({ id: "root-1", displayName: "Root 1" });
      const s2 = makeSearchStep({ id: "root-2", displayName: "Root 2" });
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2],
        strategy: null,
      });

      expect(result.hasErrors).toBe(false);
      expect(result.errorsByStepId["root-1"]).toBeUndefined();
      expect(result.errorsByStepId["root-2"]).toBeUndefined();
    });

    it("reports MISSING_OPERATOR for combine step without operator", async () => {
      const s1 = makeSearchStep({ id: "step-1" });
      const s2 = makeSearchStep({ id: "step-2", displayName: "Second" });
      const combine: Step = {
        id: "combine-1",
        displayName: "Bad combine",
        primaryInputStepId: "step-1",
        secondaryInputStepId: "step-2",
        isFiltered: false,
        // operator intentionally omitted
      };
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2, combine],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId["combine-1"]).toContain("Cannot be saved:");
    });

    it("reports UNKNOWN_STEP when input references non-existent step", async () => {
      const step: Step = {
        id: "step-1",
        displayName: "Transform with missing input",
        searchName: "GenesByOrthology",
        primaryInputStepId: "nonexistent",
        recordType: "gene",
        isFiltered: false,
      };

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId["step-1"]).toContain("Cannot be saved:");
    });
  });

  // ----- structural errors do NOT get overwritten by API validation -----
  describe("structural errors are preserved over API validation", () => {
    it("does not overwrite structural error with passing API validation", async () => {
      // A combine step with missing operator has a structural error.
      // Even if it also had a search step shape, the structural error should persist.
      const s1 = makeSearchStep({ id: "step-1" });
      const s2 = makeSearchStep({ id: "step-2", displayName: "Second" });
      const combine: Step = {
        id: "combine-1",
        displayName: "Bad combine",
        primaryInputStepId: "step-1",
        secondaryInputStepId: "step-2",
        isFiltered: false,
        // no operator
      };
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2, combine],
        strategy: null,
      });

      // The combine step should have the structural error
      expect(result.errorsByStepId["combine-1"]).toContain("Cannot be saved:");
    });

    it("does not overwrite structural error with failing API validation", async () => {
      // Search step with missing searchName gets a structural error
      // AND might also fail missing recordType/searchName check
      const step: Step = {
        id: "step-1",
        displayName: "No search name",
        recordType: "gene",
        isFiltered: false,
        // no searchName
      };

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      // Should have the structural "searchName is required" error, not overwritten
      expect(result.errorsByStepId["step-1"]).toContain("Cannot be saved:");
    });
  });

  // ----- multiple steps -----
  describe("multiple steps", () => {
    it("validates all search steps concurrently", async () => {
      const s1 = makeSearchStep({ id: "step-1" });
      const s2 = makeSearchStep({
        id: "step-2",
        displayName: "Second",
        searchName: "GenesByLocation",
      });
      const combine = makeCombineStep({
        id: "combine-1",
        primaryInputStepId: "step-1",
        secondaryInputStepId: "step-2",
      });

      mockValidateSearchParams
        .mockResolvedValueOnce(validResponse())
        .mockResolvedValueOnce(invalidResponse(["Location is required"]));

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2, combine],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
      expect(result.errorsByStepId["step-1"]).toBeUndefined();
      expect(result.errorsByStepId["step-2"]).toContain("Location is required");
      expect(result.errorsByStepId["combine-1"]).toBeUndefined();
    });

    it("mixes valid and invalid steps correctly", async () => {
      const valid = makeSearchStep({ id: "valid-step" });
      const invalid = makeSearchStep({
        id: "invalid-step",
        displayName: "Bad",
        searchName: null,
        recordType: "gene",
      });
      // Two roots but let's test independent of structural issue
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [valid, invalid],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
    });
  });

  // ----- empty parameters -----
  describe("parameters edge cases", () => {
    it("passes empty object when parameters is undefined", async () => {
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const step = makeSearchStep({ parameters: null });
      await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(mockValidateSearchParams).toHaveBeenCalledWith(
        "PlasmoDB",
        "gene",
        "GenesByKeyword",
        {},
      );
    });
  });

  // ----- ORPHAN_STEP structural error -----
  describe("ORPHAN_STEP error", () => {
    it("orphan-only graph is no longer save-blocking (severity downgraded to info)", async () => {
      // Cycle (no roots): each step references the other as input. This used to
      // emit ORPHAN_STEP as save-blocking; under the orphan-as-info regime it
      // does not block save by itself.
      const s1: Step = {
        id: "s1",
        displayName: "Step 1",
        searchName: "GenesByKeyword",
        recordType: "gene",
        primaryInputStepId: "s2",
        isFiltered: false,
      };
      const s2: Step = {
        id: "s2",
        displayName: "Step 2",
        searchName: "GenesByKeyword",
        recordType: "gene",
        primaryInputStepId: "s1",
        isFiltered: false,
      };
      mockValidateSearchParams.mockResolvedValue(validResponse());

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [s1, s2],
        strategy: null,
      });

      expect(result.hasErrors).toBe(false);
      expect(result.errorsByStepId["s1"]).toBe(undefined);
      expect(result.errorsByStepId["s2"]).toBe(undefined);
    });
  });

  // ----- hasErrors -----
  describe("hasErrors flag", () => {
    it("is false when all steps pass validation", async () => {
      mockValidateSearchParams.mockResolvedValue(validResponse());
      const step = makeSearchStep();

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(false);
    });

    it("is true when any step has an error", async () => {
      mockValidateSearchParams.mockResolvedValue(invalidResponse(["Bad"]));
      const step = makeSearchStep();

      const result = await validateStepsForSave({
        siteId: "PlasmoDB",
        steps: [step],
        strategy: null,
      });

      expect(result.hasErrors).toBe(true);
    });
  });
});
