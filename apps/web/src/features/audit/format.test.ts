import { describe, expect, it } from "vitest";
import type { RateBounds } from "@pathfinder/shared/generated/types/RateBounds";

import served from "../../../../../packages/spec/audit_words.json";

import {
  dayText,
  impactText,
  joinWords,
  percent,
  plural,
  rangeText,
  rateText,
  scopeText,
  shareText,
  unresolvedText,
} from "./format";

const NF54_LENGTHS: RateBounds = {
  confirmed: 3,
  checked: 10,
  unresolved: 2,
  rate: 0.3,
  low: 0.10779,
  high: 0.60323,
  floor: 0.25,
  ceiling: 0.41667,
};

describe("audit formats", () => {
  it("reads a rate of 3 errors in 10 checked as the Wilson interval states it", () => {
    expect(shareText(NF54_LENGTHS)).toBe("3 of 10");
    expect(rateText(NF54_LENGTHS)).toBe("30% (11% to 60%)");
    expect(rangeText(NF54_LENGTHS)).toBe("25% to 42%");
    expect(percent(1)).toBe("100%");
  });

  it("rounds a share that falls on a half to the even percent, as the API does", () => {
    expect([percent(0.125), percent(0.375), percent(0.135), percent(0)]).toEqual([
      "12%",
      "38%",
      "14%",
      "0%",
    ]);
  });

  it("counts, lists and dates in plain words", () => {
    expect([plural(1, "finding"), plural(4300, "base")]).toEqual([
      "1 finding",
      "4,300 bases",
    ]);
    expect(plural(0, "finding")).toBe("0 findings");
    expect(plural(2, "piece of evidence", "pieces of evidence")).toBe(
      "2 pieces of evidence",
    );
    expect(plural(1, "piece of evidence", "pieces of evidence")).toBe(
      "1 piece of evidence",
    );
    expect([
      joinWords([]),
      joinWords(["a"]),
      joinWords(["a", "b"]),
      joinWords(["a", "b", "c"]),
    ]).toEqual(["", "a", "a and b", "a, b and c"]);
    expect(dayText("2026-10-22T00:00:00Z")).toBe("Oct 22, 2026");
    expect(dayText("2026-10-22T23:30:00-05:00")).toBe("Oct 23, 2026");
    expect([impactText(null), impactText(0.075), impactText(0.5)]).toEqual([
      "Not weighed",
      "0.075",
      "0.5",
    ]);
  });

  it("states a run's scope and an unresolved count by status", () => {
    expect(scopeText({ genomes: ["Plasmodium falciparum NF54"], targets: 2 })).toBe(
      "Plasmodium falciparum NF54 and 2 gene targets",
    );
    expect(
      unresolvedText(
        {
          screened: 0,
          unsampled: 1,
          trying: 0,
          failed: 0,
          unreached: 1,
          unread: 1,
          total: 3,
        },
        served.unresolved,
      ),
    ).toBe(
      "3 (1 not in the random sample, 1 where the site did not answer, 1 not read before the run's deadline)",
    );
    expect(
      unresolvedText(
        {
          screened: 0,
          unsampled: 0,
          trying: 0,
          failed: 0,
          unreached: 0,
          unread: 0,
          total: 0,
        },
        served.unresolved,
      ),
    ).toBe("0");
  });

  it("names the genomes alone, or one gene target, in a run's scope", () => {
    expect(scopeText({ genomes: ["NF54", "3D7"], targets: 0 })).toBe("NF54 and 3D7");
    expect(scopeText({ genomes: ["NF54", "3D7"], targets: 1 })).toBe(
      "NF54, 3D7 and 1 gene target",
    );
  });

  it("names the unresolved statuses in the order the API serves their words", () => {
    const { unread, ...rest } = served.unresolved;
    expect(
      unresolvedText({ screened: 4, unread: 6, total: 10 }, { unread, ...rest }),
    ).toBe("10 (6 not read before the run's deadline, 4 not checked yet)");
  });

  it("names every unresolved status, in the order a finding moves through them", () => {
    expect(
      unresolvedText(
        {
          screened: 4,
          unsampled: 5,
          trying: 1,
          failed: 2,
          declined: 7,
          unreached: 3,
          unread: 6,
          total: 28,
        },
        served.unresolved,
      ),
    ).toBe(
      "28 (4 not checked yet, 5 not in the random sample, 1 being checked, 2 where the check failed, 7 that the check does not take, 3 where the site did not answer, 6 not read before the run's deadline)",
    );
  });

  it("reads a status the API leaves out as none", () => {
    expect(unresolvedText({ failed: 2, total: 2 }, served.unresolved)).toBe(
      "2 (2 where the check failed)",
    );
  });
});
