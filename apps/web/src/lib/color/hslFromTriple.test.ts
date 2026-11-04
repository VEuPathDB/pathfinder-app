import { describe, expect, it } from "vitest";
import { parse } from "zrender/lib/tool/color.js";

import { hslFromTriple } from "./hsl";

describe("hslFromTriple", () => {
  it("writes a color the chart library can blend", () => {
    expect(parse(hslFromTriple("0 0% 100%"), [])).toEqual([255, 255, 255, 1]);
    expect(parse(hslFromTriple("215 75% 44%"), [])).toEqual([28, 98, 196, 1]);
  });
});
