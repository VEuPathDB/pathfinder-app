import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { paramValueToRaw, rawToParamValue } from "./paramValue";
import type { ParamSpec } from "./spec";

/**
 * `rawToParamValue` and `paramValueToRaw` are inverses in the editor: the form
 * holds raw strings, the step holds typed values, and every keystroke crosses
 * both. Nothing asserted that the pair agreed, so a value could survive the
 * trip changed.
 *
 * These are the properties the pair has to satisfy for the editor to be
 * lossless. Ranges are the interesting case: the encoding joins min and max
 * with "-", which is also what a negative number starts with.
 */

function spec(type: ParamSpec["type"]): ParamSpec {
  return { name: "p", displayName: "P", type, required: false } as ParamSpec;
}

describe("paramValue round trip", () => {
  it("preserves a string", () => {
    fc.assert(
      fc.property(fc.string(), (value) => {
        const parsed = rawToParamValue(spec("string"), value);
        expect(paramValueToRaw(parsed)).toBe(value);
      }),
    );
  });

  it("preserves a multi-pick selection, including the empty one", () => {
    fc.assert(
      fc.property(fc.array(fc.string({ minLength: 1 })), (values) => {
        const parsed = rawToParamValue(spec("multi-pick-vocabulary"), values);
        expect(paramValueToRaw(parsed)).toEqual(values);
      }),
    );
  });

  it("preserves a finite number", () => {
    fc.assert(
      fc.property(fc.integer(), (value) => {
        const parsed = rawToParamValue(spec("number"), String(value));
        expect(paramValueToRaw(parsed)).toBe(String(value));
      }),
    );
  });

  it("preserves a non-negative number range", () => {
    fc.assert(
      fc.property(fc.nat({ max: 100000 }), fc.nat({ max: 100000 }), (min, max) => {
        const raw = `${min}:${max}`;
        const parsed = rawToParamValue(spec("number-range"), raw);
        expect(paramValueToRaw(parsed)).toBe(raw);
      }),
    );
  });

  it("preserves a range whose lower bound is negative", () => {
    // Fold change thresholds are routinely negative: "-2 to 2" is an ordinary
    // differential-expression cutoff, so this is not a synthetic edge case.
    const raw = "-2:2";

    const parsed = rawToParamValue(spec("number-range"), raw);

    expect(parsed).toEqual({ type: "number-range", min: -2, max: 2 });
  });

  it("preserves a date range, whose bounds contain hyphens", () => {
    const raw = "2026-01-01:2026-12-31";

    const parsed = rawToParamValue(spec("date-range"), raw);

    expect(parsed).toEqual({
      type: "date-range",
      min: "2026-01-01",
      max: "2026-12-31",
    });
  });

  it("preserves a filter list", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            field: fc.string({ minLength: 1 }),
            type: fc.constant("string"),
            isRange: fc.constant(false),
            includeUnknown: fc.boolean(),
            value: fc.array(fc.string()),
          }),
        ),
        (filters) => {
          const raw = JSON.stringify({ filters });
          const parsed = rawToParamValue(spec("filter"), raw);
          expect(paramValueToRaw(parsed)).toBe(raw);
        },
      ),
    );
  });
});
