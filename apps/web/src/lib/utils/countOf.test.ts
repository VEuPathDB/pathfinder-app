import { describe, expect, it } from "vitest";

import { countOf } from "./countOf";

describe("countOf", () => {
  it("names one and many with digit separators", () => {
    expect([countOf(1, "filter", "filters"), countOf(47668, "gene", "genes")]).toEqual([
      "1 filter",
      "47,668 genes",
    ]);
  });
});
