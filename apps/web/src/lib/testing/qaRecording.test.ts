import { describe, expect, it } from "vitest";

import { qaRecording } from "./qaRecording";

const present = qaRecording(import.meta.url, "../../../package.json");
const absent = qaRecording(import.meta.url, "./absent-recording.json");

describe("qaRecording", () => {
  it("reads a recording that is present", () => {
    expect(present).toMatchObject({ name: "pathfinder-web" });
  });

  it("answers null for a recording that is gone, beside a skip that names why", () => {
    expect(absent).toBe(null);
  });
});
