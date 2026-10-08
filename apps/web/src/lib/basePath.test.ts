import { describe, expect, it } from "vitest";

import { BASE_PATH, withBasePath } from "./basePath";

describe("withBasePath", () => {
  it("puts an absolute app path under the base path", () => {
    expect(withBasePath("/plasmodb/conversation")).toBe(
      "/pathfinder/plasmodb/conversation",
    );
  });

  it("leaves a path that already carries the base path alone", () => {
    expect(withBasePath(`${BASE_PATH}/x`)).toBe("/pathfinder/x");
  });
});
