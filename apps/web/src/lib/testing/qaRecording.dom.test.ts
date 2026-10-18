/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";

import { qaRecording } from "./qaRecording";

const present = qaRecording(import.meta.url, "../../../package.json");

describe("qaRecording in a page environment", () => {
  it("reads a recording that is present", () => {
    expect(present).toMatchObject({ name: "pathfinder-web" });
  });
});
