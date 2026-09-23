import { describe, expect, it } from "vitest";

import { comparisonLine, higherIn } from "./comparison";

const PBM = { groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] };

describe("comparisonLine", () => {
  it("names every label of each group, group A first", () => {
    expect(
      comparisonLine({ groupA: ["24h pbm"], groupB: ["18h pbm", "36h pbm"] }),
    ).toBe("Group A: 24h pbm - Group B: 18h pbm, 36h pbm");
  });
});

describe("higherIn", () => {
  it("names the positive side by group B's labels", () => {
    expect(higherIn(PBM, "B")).toBe("Higher in 18h pbm, 36h pbm");
  });

  it("names the negative side by group A's labels", () => {
    expect(higherIn(PBM, "A")).toBe("Higher in 24h pbm");
  });

  it("names the group letter when the plot carries no comparison", () => {
    expect(higherIn(null, "B")).toBe("Higher in group B");
  });
});
