import { describe, expect, it } from "vitest";

import { qaRecording } from "./qaRecording";

const present = qaRecording(new URL("../../../package.json", import.meta.url));
const absent = qaRecording(new URL("./absent-recording.json", import.meta.url));

describe("qaRecording", () => {
  it("reads a recording that is present", () => {
    expect(present).toMatchObject({ name: "pathfinder-web" });
  });

  it("answers null for a recording that is gone, beside a skip that names why", () => {
    expect(absent).toBe(null);
  });
});
