import { afterEach, describe, expect, it, vi } from "vitest";

import { aNewerBuildIsServed, currentWebBuild } from "./webBuild";

describe("the web build", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is the build id the image was built with", () => {
    vi.stubEnv("PATHFINDER_WEB_BUILD", "3f9a1c0be2d4");

    expect(currentWebBuild()).toBe("3f9a1c0be2d4");
  });

  it("is empty for a build that names none", () => {
    vi.stubEnv("PATHFINDER_WEB_BUILD", "");

    expect(currentWebBuild()).toBe("");
  });

  it.each([
    ["3f9a1c0be2d4", "77b0e5a91c3f", true],
    ["3f9a1c0be2d4", "3f9a1c0be2d4", false],
    ["", "77b0e5a91c3f", false],
    ["3f9a1c0be2d4", "", false],
  ])("a tab on %j served %j is behind: %j", (mine, served, behind) => {
    expect(aNewerBuildIsServed({ mine, served })).toBe(behind);
  });

  it("reads the variable in the dotted form the Next build inlines", () => {
    expect(currentWebBuild.toString()).toContain("process.env.PATHFINDER_WEB_BUILD");
  });
});
