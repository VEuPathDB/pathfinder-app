import { describe, expect, it } from "vitest";

import { threadModeEnum } from "@pathfinder/shared/generated/types/ThreadMode";

import { nextThreadMode } from "./threadModes";

describe("nextThreadMode", () => {
  it("cycles auto, explore, build and back", () => {
    expect(Object.values(threadModeEnum).map(nextThreadMode)).toEqual([
      "explore",
      "build",
      "auto",
    ]);
  });
});
