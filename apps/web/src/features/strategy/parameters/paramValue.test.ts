import { describe, expect, it } from "vitest";
import type { ParamSpec } from "@strategist/shared";

import { paramValueToRaw, rawToParamValue } from "./paramValue";
import { encodeRange } from "./rangeCodec";
import type { ParamValue } from "@/lib/parameters/paramValue";

const spec = (type: string): ParamSpec => ({ type }) as unknown as ParamSpec;

const VARIANTS_FROM_SIX_RAW =
  '{"filters":[{"field":"total_variants","type":"number","isRange":true,"includeUnknown":false,"value":{"min":6}}]}';
const VARIANTS_FROM_SIX = {
  field: "total_variants",
  type: "number",
  isRange: true,
  includeUnknown: false,
  value: { min: 6 },
} as const;

describe("paramValueToRaw - typed value -> WDK raw", () => {
  it("stringifies a number (dN/dS cutoff)", () => {
    expect(paramValueToRaw({ type: "number", value: 1.3 })).toBe("1.3");
  });

  it("passes a multi-pick vocabulary through as an array", () => {
    expect(
      paramValueToRaw({
        type: "multi-pick-vocabulary",
        values: ["Plasmodium falciparum 3D7", "Plasmodium berghei"],
      }),
    ).toEqual(["Plasmodium falciparum 3D7", "Plasmodium berghei"]);
  });

  it("encodes a number range as min:max", () => {
    expect(paramValueToRaw({ type: "number-range", min: 2, max: 8 })).toBe("2:8");
  });

  it("writes no filters as the value WDK defaults a filter parameter to", () => {
    expect(paramValueToRaw({ type: "filter", filters: [] })).toBe('{"filters":[]}');
  });

  it("writes filter clauses as the WDK filter value", () => {
    const raw = paramValueToRaw({ type: "filter", filters: [VARIANTS_FROM_SIX] });
    expect(raw).toBe(VARIANTS_FROM_SIX_RAW);
  });
});

describe("rawToParamValue - WDK raw -> typed value", () => {
  it("coerces a numeric string to a number value", () => {
    expect(rawToParamValue(spec("number"), "1.3")).toEqual({
      type: "number",
      value: 1.3,
    });
  });

  it("splits a min:max string into numeric bounds", () => {
    expect(rawToParamValue(spec("number-range"), "2:8")).toEqual({
      type: "number-range",
      min: 2,
      max: 8,
    });
  });

  it("wraps a lone vocabulary string as a single-element multi-pick array", () => {
    expect(rawToParamValue(spec("multi-pick-vocabulary"), "product")).toEqual({
      type: "multi-pick-vocabulary",
      values: ["product"],
    });
  });

  it("keeps each clause of a WDK filter value", () => {
    expect(rawToParamValue(spec("filter"), VARIANTS_FROM_SIX_RAW)).toEqual({
      type: "filter",
      filters: [VARIANTS_FROM_SIX],
    });
  });

  it("refuses a filter clause that names no type", () => {
    const untyped = '{"filters":[{"field":"organism","isRange":false,"value":["a"]}]}';
    expect(() => rawToParamValue(spec("filter"), untyped)).toThrow();
  });
});

describe("round-trips preserve the value", () => {
  const cases: ParamValue[] = [
    { type: "string", value: "kinase" },
    { type: "number", value: 1.3 },
    { type: "single-pick-vocabulary", value: "Biological Process" },
    {
      type: "multi-pick-vocabulary",
      values: ["Plasmodium falciparum 3D7", "Plasmodium berghei"],
    },
    { type: "number-range", min: 2, max: 8 },
    { type: "filter", filters: [VARIANTS_FROM_SIX] },
  ];

  it.each(cases)("$type survives raw round-trip", (value) => {
    const roundTripped = rawToParamValue(spec(value.type), paramValueToRaw(value));
    expect(roundTripped).toEqual(value);
  });
});

describe("an empty number or date", () => {
  it("goes out as the empty raw value", () => {
    expect(paramValueToRaw({ type: "number", value: null })).toBe("");
    expect(paramValueToRaw({ type: "date", value: null })).toBe("");
  });

  it("reads an empty field as no value, never as zero", () => {
    expect(rawToParamValue(spec("number"), "")).toEqual({
      type: "number",
      value: null,
    });
    expect(rawToParamValue(spec("date"), "")).toEqual({ type: "date", value: null });
  });
});

describe("an empty filter is not a filter with no clauses", () => {
  it("goes out as the empty raw value", () => {
    expect(paramValueToRaw({ type: "filter", filters: [], empty: true })).toBe("");
    expect(paramValueToRaw({ type: "filter", filters: [] })).toBe('{"filters":[]}');
  });

  it("reads each raw value back as its own value", () => {
    expect(rawToParamValue(spec("filter"), "")).toEqual({
      type: "filter",
      filters: [],
      empty: true,
    });
    expect(rawToParamValue(spec("filter"), '{"filters":[]}')).toEqual({
      type: "filter",
      filters: [],
    });
  });
});

describe("a number field that holds no number", () => {
  const named = { type: "number", name: "min_weight" } as unknown as ParamSpec;
  const range = { type: "number-range", name: "length_range" } as unknown as ParamSpec;

  it("is refused by name, never saved as an empty value", () => {
    expect(() => rawToParamValue(named, "1e")).toThrow("min_weight");
    expect(() => rawToParamValue(range, encodeRange("1e", "5"))).toThrow(
      "length_range",
    );
  });
});

describe("a held value", () => {
  const held: ParamValue = { type: "held", wire: '["Pf3D7", "PvP01"' };

  it("is its raw text in a single field and one term in a multi-pick", () => {
    expect(paramValueToRaw(held, spec("string"))).toBe('["Pf3D7", "PvP01"');
    expect(paramValueToRaw(held, spec("multi-pick-vocabulary"))).toEqual([
      '["Pf3D7", "PvP01"',
    ]);
  });
});
