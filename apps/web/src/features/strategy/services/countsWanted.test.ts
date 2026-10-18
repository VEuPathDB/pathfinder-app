import { describe, expect, it } from "vitest";

import { countsWanted } from "./countsWanted";

describe("countsWanted", () => {
  it("wants nothing when the save counted every step", () => {
    expect(
      countsWanted({
        steps: [{ estimatedSize: 120 }, { estimatedSize: 7 }],
        savesInFlight: 0,
      }),
    ).toBe(false);
  });

  it("takes a count of zero as a count", () => {
    expect(countsWanted({ steps: [{ estimatedSize: 0 }], savesInFlight: 0 })).toBe(
      false,
    );
  });

  it("wants counts when a step has none", () => {
    expect(
      countsWanted({
        steps: [{ estimatedSize: 120 }, { estimatedSize: null }],
        savesInFlight: 0,
      }),
    ).toBe(true);
  });

  it("wants counts when a step was never counted", () => {
    expect(
      countsWanted({ steps: [{ estimatedSize: 120 }, {}], savesInFlight: 0 }),
    ).toBe(true);
  });

  it("waits while a save is in flight, because the save answers with counts", () => {
    expect(countsWanted({ steps: [{ estimatedSize: null }], savesInFlight: 1 })).toBe(
      false,
    );
  });

  it("wants nothing for a strategy with no steps", () => {
    expect(countsWanted({ steps: [], savesInFlight: 0 })).toBe(false);
  });
});
