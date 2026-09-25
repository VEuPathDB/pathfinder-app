import { describe, expect, it } from "vitest";
import { siteShortName } from "@pathfinder/shared";

describe("siteShortName", () => {
  // A link reads "Open in PlasmoDB". The long form carries the organism in
  // parentheses, which belongs in a picker rather than on a link.
  it("gives the brand name, not the long form", () => {
    expect(siteShortName("plasmodb")).toBe("PlasmoDB");
  });

  it("names the portal", () => {
    expect(siteShortName("veupathdb")).toBe("VEuPathDB");
  });

  it("names a component site by its brand alone", () => {
    expect(siteShortName("toxodb")).toBe("ToxoDB");
  });

  it("falls back to the id for a site it does not know", () => {
    expect(siteShortName("notasite")).toBe("notasite");
  });

  it("falls back to the id for an empty site", () => {
    expect(siteShortName("")).toBe("");
  });
});
