import { describe, expect, it } from "vitest";

import { THREAD_MODES, nextThreadMode } from "./threadModes";

describe("nextThreadMode", () => {
  it("cycles auto, explore, build and back", () => {
    expect(THREAD_MODES.map(nextThreadMode)).toEqual(["explore", "build", "auto"]);
  });
});
