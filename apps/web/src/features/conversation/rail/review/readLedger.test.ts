import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";

import { groundedEntry, makeLedger } from "./ledgerFixture";
import { latestLedgerView, readLedger } from "./readLedger";

const CONTROLS_CAVEAT = {
  kind: "controls",
  sentence: "2 of 3 positive controls were returned.",
};

function withRetiredKind<T extends object>(value: T): unknown {
  return JSON.parse(JSON.stringify(value).replace('"kind":"text"', '"kind":"other"'));
}

describe("readLedger", () => {
  it("reads a current payload", () => {
    const ledger = makeLedger({
      constraints: {
        grounded: [groundedEntry("taxonomic scope", "grounded")],
        unmetCount: 0,
        blocking: false,
      },
    });

    const view = readLedger(ledger);

    expect(view?.userIntent?.inferredGoal).toBe(
      "Identify transporter genes across Apicomplexa",
    );
    expect([view?.frame?.present, view?.build?.succeeded]).toEqual([true, true]);
    expect(view?.constraints?.grounded?.map((g) => g.constraint.label)).toEqual([
      "taxonomic scope",
    ]);
  });

  it("keeps other sections when one is unreadable", () => {
    const ledger = makeLedger();
    const raw = { ...ledger, build: { succeeded: "maybe" } };

    const view = readLedger(raw);

    expect(view?.build).toBeNull();
    expect(view?.userIntent?.inferredGoal).toBe(
      "Identify transporter genes across Apicomplexa",
    );
    expect(view?.frame?.readyToBuild).toBe(true);
  });

  it("keeps the question when one stated constraint has a retired kind", () => {
    const intent = makeLedger().userIntent;
    const raw = {
      ...makeLedger(),
      userIntent: {
        ...intent,
        explicitConstraints: [
          { kind: "organism", requestedValue: "Apicomplexa", label: "scope" },
          withRetiredKind({ kind: "text", requestedValue: "x", label: "words" }),
        ],
      },
    };

    const view = readLedger(raw);

    expect(view?.userIntent?.inferredGoal).toBe(
      "Identify transporter genes across Apicomplexa",
    );
    expect(view?.userIntent?.explicitConstraints?.map((c) => c.label)).toEqual([
      "scope",
    ]);
  });

  it("drops only the unreadable grounded entry", () => {
    const raw = {
      ...makeLedger(),
      constraints: {
        grounded: [
          groundedEntry("taxonomic scope", "grounded"),
          withRetiredKind(groundedEntry("annotation words", "grounded")),
        ],
        unmetCount: 0,
        blocking: false,
      },
    };

    const view = readLedger(raw);

    expect(view?.constraints?.grounded?.map((g) => g.constraint.label)).toEqual([
      "taxonomic scope",
    ]);
  });

  it("drops only the unreadable caveat", () => {
    const raw = {
      ...makeLedger(),
      verification: {
        complete: true,
        successful: true,
        caveats: [CONTROLS_CAVEAT, { kind: "retired_kind", sentence: "old" }],
      },
    };

    const view = readLedger(raw);

    expect(view?.verification?.caveats?.map((c) => c.sentence)).toEqual([
      CONTROLS_CAVEAT.sentence,
    ]);
  });

  it("drops only the unreadable digest gap", () => {
    const raw = {
      ...makeLedger(),
      verification: {
        complete: true,
        successful: true,
        digest: {
          prose: "The check read the records.",
          gaps: [
            { kind: "requirement", text: "stage", sentence: "Stage has no search." },
            { kind: "retired_gap", sentence: "old" },
          ],
          caveats: [CONTROLS_CAVEAT, { kind: "retired_kind", sentence: "old" }],
        },
      },
    };

    const digest = readLedger(raw)?.verification?.digest;

    expect([
      digest?.gaps?.map((g) => g.sentence),
      digest?.caveats?.map((c) => c.sentence),
    ]).toEqual([["Stage has no search."], [CONTROLS_CAVEAT.sentence]]);
  });

  it("keeps a failed step when another node carries a retired status", () => {
    const raw = {
      ...makeLedger(),
      build: {
        ...makeLedger().build,
        succeeded: false,
        nodeResults: [
          {
            nodeId: "s1",
            searchName: "GenesByText",
            status: "failed",
            error: "Refused.",
          },
          { nodeId: "s2", searchName: "GenesByTaxon", status: "retired_status" },
        ],
      },
    };

    expect(readLedger(raw)?.build?.nodeResults.map((n) => n.error)).toEqual([
      "Refused.",
    ]);
  });

  it("returns null for a non-object", () => {
    expect([readLedger("x"), readLedger(null)]).toEqual([null, null]);
  });
});

describe("latestLedgerView", () => {
  it("takes the newest readable update", () => {
    const older = makeLedger();
    const messages = [
      {
        id: "a",
        role: "assistant",
        parts: [{ type: "data-ledger-update", data: older }],
      },
      {
        id: "b",
        role: "assistant",
        parts: [{ type: "data-ledger-update", data: "not a ledger" }],
      },
    ] as unknown as UIMessage[];

    expect(latestLedgerView(messages)?.userIntent?.inferredGoal).toBe(
      older.userIntent?.inferredGoal,
    );
  });
});
