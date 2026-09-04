import { describe, expect, it } from "vitest";
import type { ParamSpec } from "@pathfinder/shared";

import { paramValueToRaw, rawToParamValue } from "./paramValue";
import type { ParamValue } from "@/lib/parameters/paramValue";

const spec = (type: string): ParamSpec => ({ type }) as unknown as ParamSpec;

describe("paramValueToRaw — typed value → WDK raw", () => {
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

  it("serializes filter clauses as JSON", () => {
    const raw = paramValueToRaw({
      type: "filter",
      filters: [{ field: "stage", value: "trophozoite" }],
    } as unknown as ParamValue);
    expect(raw).toBe('[{"field":"stage","value":"trophozoite"}]');
  });
});

describe("rawToParamValue — WDK raw → typed value", () => {
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

  it("parses filter JSON back into clauses", () => {
    expect(
      rawToParamValue(spec("filter"), '[{"field":"stage","value":"trophozoite"}]'),
    ).toEqual({
      type: "filter",
      filters: [{ field: "stage", value: "trophozoite" }],
    });
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
  ];

  it.each(cases)("$type survives raw round-trip", (value) => {
    const roundTripped = rawToParamValue(spec(value.type), paramValueToRaw(value));
    expect(roundTripped).toEqual(value);
  });
});
