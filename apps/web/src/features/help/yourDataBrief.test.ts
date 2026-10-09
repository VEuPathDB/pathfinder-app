import { describe, expect, it } from "vitest";

import { DATA_STATEMENT_VERSION } from "@pathfinder/shared";

import { YOUR_DATA_IN_BRIEF, YOUR_DATA_LAST_UPDATED } from "./yourDataBrief";

describe("the data statement in brief", () => {
  it("dates the statement by the version the api serves", () => {
    expect(DATA_STATEMENT_VERSION).toBe("2026-10-09");
    expect(YOUR_DATA_LAST_UPDATED).toBe("October 9, 2026");
  });

  it("states seven points a reader can take in at a glance", () => {
    expect(YOUR_DATA_IN_BRIEF).toHaveLength(7);
    expect(YOUR_DATA_IN_BRIEF[0]).toMatch(/^Your messages, the files you attach/);
    expect(YOUR_DATA_IN_BRIEF.at(-1)).toBe(
      "Questions or concerns: write to help@veupathdb.org.",
    );
  });
});
