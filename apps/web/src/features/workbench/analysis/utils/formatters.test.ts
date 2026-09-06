import { describe, it, expect } from "vitest";
import { pct, fmtNum, fmtParamValue } from "./formatters";

describe("pct", () => {
  it("formats a decimal as a percentage", () => {
    expect(pct(0.5)).toBe("50.0%");
  });

  it("formats 0 as 0.0%", () => {
    expect(pct(0)).toBe("0.0%");
  });

  it("formats 1 as 100.0%", () => {
    expect(pct(1)).toBe("100.0%");
  });

  it("formats a small decimal with one decimal place", () => {
    expect(pct(0.123)).toBe("12.3%");
  });

  it("rounds to one decimal place", () => {
    expect(pct(0.1256)).toBe("12.6%");
  });

  it("returns em-dash for null", () => {
    expect(pct(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(pct(undefined)).toBe("\u2014");
  });

  it("handles negative values", () => {
    expect(pct(-0.05)).toBe("-5.0%");
  });

  it("handles values greater than 1", () => {
    expect(pct(1.5)).toBe("150.0%");
  });

  it("handles very small values", () => {
    expect(pct(0.001)).toBe("0.1%");
  });

  it("handles NaN input", () => {
    // NaN * 100 = NaN, toFixed(1) => "NaN"
    expect(pct(NaN)).toBe("NaN%");
  });

  it("handles Infinity", () => {
    expect(pct(Infinity)).toBe("Infinity%");
  });
});

describe("fmtNum", () => {
  it("formats a number with default 3 decimal places", () => {
    expect(fmtNum(1.23456)).toBe("1.235");
  });

  it("formats 0 correctly", () => {
    expect(fmtNum(0)).toBe("0.000");
  });

  it("returns em-dash for null", () => {
    expect(fmtNum(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(fmtNum(undefined)).toBe("\u2014");
  });

  it("respects custom decimal places", () => {
    expect(fmtNum(3.14159, 2)).toBe("3.14");
  });

  it("handles 0 decimal places", () => {
    expect(fmtNum(3.7, 0)).toBe("4");
  });

  it("handles negative numbers", () => {
    expect(fmtNum(-2.5)).toBe("-2.500");
  });

  it("pads with zeros when needed", () => {
    expect(fmtNum(1, 5)).toBe("1.00000");
  });

  it("handles very large numbers", () => {
    expect(fmtNum(1e10, 1)).toBe("10000000000.0");
  });

  it("handles very small numbers", () => {
    expect(fmtNum(0.0001, 4)).toBe("0.0001");
  });

  it("handles NaN input", () => {
    expect(fmtNum(NaN)).toBe("NaN");
  });

  it("rounds correctly at boundary", () => {
    // IEEE 754: 1.0005 is stored as slightly less than 1.0005, so toFixed(3) => "1.000"
    expect(fmtNum(1.0005, 3)).toBe("1.000");
    // A value that rounds up unambiguously
    expect(fmtNum(1.0055, 2)).toBe("1.01");
  });
});

describe("fmtParamValue", () => {
  it("prints integers without decimals", () => {
    expect(fmtParamValue(5)).toBe("5");
    expect(fmtParamValue(0)).toBe("0");
  });

  it("prints fractions with 2 decimals", () => {
    expect(fmtParamValue(0.05)).toBe("0.05");
    expect(fmtParamValue(1.239)).toBe("1.24");
  });
});
