import { describe, expect, it } from "vitest";

import { formatCost, formatTokens, formatUsage } from "./usageFormat";

describe("formatTokens", () => {
  it("compacts large token counts", () => {
    expect(formatTokens(49401)).toBe("49.4K");
    expect(formatTokens(245742)).toBe("245.7K");
    expect(formatTokens(500)).toBe("500");
  });
});

describe("formatCost", () => {
  it("shows two decimals for normal costs", () => {
    expect(formatCost(0.023)).toBe("$0.02");
    expect(formatCost(1.5)).toBe("$1.50");
  });

  it("shows extra precision for sub-cent costs", () => {
    expect(formatCost(0.0008)).toBe("$0.0008");
  });

  it("clamps non-positive to $0.00", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(-1)).toBe("$0.00");
  });
});

describe("formatUsage", () => {
  it("joins compact tokens and cost", () => {
    expect(formatUsage(12300, "0.004")).toBe("12.3K, $0.004");
    expect(formatUsage(49401, 0.0228)).toBe("49.4K, $0.02");
    expect(formatUsage(41800, "0.0131")).toBe("41.8K, $0.01");
  });
});
