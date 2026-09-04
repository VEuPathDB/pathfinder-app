import { describe, it, expect } from "vitest";
import { formatCompactClean, formatPrice } from "./format";

describe("formatCompactClean", () => {
  it("trims .0 for round millions", () => {
    expect(formatCompactClean(1_000_000)).toBe("1M");
    expect(formatCompactClean(2_000_000)).toBe("2M");
  });

  it("keeps decimal for non-round millions", () => {
    expect(formatCompactClean(1_500_000)).toBe("1.5M");
  });

  it("trims .0 for round thousands", () => {
    expect(formatCompactClean(128_000)).toBe("128K");
    expect(formatCompactClean(1_000)).toBe("1K");
  });

  it("keeps decimal for non-round thousands", () => {
    expect(formatCompactClean(1_500)).toBe("1.5K");
  });

  it("returns plain string for small numbers", () => {
    expect(formatCompactClean(42)).toBe("42");
  });
});

describe("formatPrice", () => {
  it('returns "Free" for zero', () => {
    expect(formatPrice(0)).toBe("Free");
  });

  it("shows <$0.01 for tiny prices", () => {
    expect(formatPrice(0.005)).toBe("<$0.01");
  });

  it("shows 2 decimal places for normal prices", () => {
    expect(formatPrice(3.0)).toBe("$3.00");
    expect(formatPrice(0.15)).toBe("$0.15");
  });
});
