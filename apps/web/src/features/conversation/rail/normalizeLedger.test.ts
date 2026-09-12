import { describe, expect, it } from "vitest";
import { normalizeLedgerPayload } from "./normalizeLedger";

const INTENT = {
  classification: "new_strategy",
  inferredGoal: "find gametocyte genes",
  isDifferential: true,
  differentialSides: ["female", "male"],
};

const FRAME = {
  spec: {
    goal: "find gametocyte genes",
    interpretedGoal: "find gametocyte genes",
    recordType: "transcript",
    title: "Gametocyte genes",
    criteria: [],
    dropped: [],
    openSlots: [],
  },
  present: true,
  diff: null,
  criteriaCount: 1,
  boundCount: 2,
  openSlotCount: 0,
  droppedCount: 0,
  readyToBuild: true,
  needsUser: false,
  contrasts: [],
  structureRender: null,
};

const BUILD = {
  outcome: null,
  staleBuild: null,
  pushedCount: 1,
  failedCount: 0,
  skippedCount: 0,
  zeroResultSteps: [],
  needsRecovery: false,
  recoveryKind: "none",
  succeeded: true,
  nodeResults: [],
  wdkStrategyId: null,
  wdkUrl: null,
};

const WIRE = {
  userIntent: INTENT,
  frame: FRAME,
  build: BUILD,
  verification: { digest: null, complete: false, successful: false },
  constraints: { grounded: [], unmetCount: 0, blocking: false },
};

describe("normalizeLedgerPayload", () => {
  it("reads a full wire payload", () => {
    const result = normalizeLedgerPayload(WIRE);

    expect(result?.userIntent?.inferredGoal).toBe("find gametocyte genes");
    expect(result?.frame.criteriaCount).toBe(1);
    expect(result?.frame.structureRender).toBe(null);
    expect(result?.build.pushedCount).toBe(1);
    expect(result?.build.wdkStrategyId).toBe(null);
    expect(result?.verification.digest).toBe(null);
    expect(result?.constraints?.grounded).toEqual([]);
  });

  it("returns null for an unreadable payload", () => {
    expect(normalizeLedgerPayload(undefined)).toBe(null);
    expect(normalizeLedgerPayload(null)).toBe(null);
    expect(normalizeLedgerPayload("ledger")).toBe(null);
    expect(normalizeLedgerPayload([])).toBe(null);
    expect(normalizeLedgerPayload({})).toBe(null);
    expect(
      normalizeLedgerPayload({ ...WIRE, frame: { ...FRAME, criteriaCount: "many" } }),
    ).toBe(null);
  });
});
