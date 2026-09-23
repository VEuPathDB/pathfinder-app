import { describe, expect, it } from "vitest";

import { siteLinkTarget } from "./siteLinkTarget";

describe("siteLinkTarget", () => {
  it("opens a new tab when PathFinder is the top window", () => {
    const page = {};
    expect(siteLinkTarget(page, page)).toBe("_blank");
  });

  it("replaces the embedding page when PathFinder runs inside a frame", () => {
    expect(siteLinkTarget({}, {})).toBe("_top");
  });

  it("replaces the embedding page when the top window is out of reach", () => {
    expect(siteLinkTarget({}, null)).toBe("_top");
  });
});
