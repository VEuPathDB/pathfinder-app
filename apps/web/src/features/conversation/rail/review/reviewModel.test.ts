import { describe, expect, it } from "vitest";
import type { EvidenceCard, Strategy } from "@strategist/shared";

import { phaseLabel } from "@/lib/models/phaseRoles";

import { EVIDENCE_CARD } from "../../content/parts/evidenceCardFixture";
import { groundedEntry, makeLedger, SAMPLE_CAVEAT_SENTENCE } from "./ledgerFixture";
import { readLedger, type LedgerView } from "./readLedger";
import { reviewModel, type ReviewInput } from "./reviewModel";

const STRATEGY: Strategy = {
  id: "c1",
  name: "Transporters",
  siteId: "plasmodb",
  recordType: "transcript",
  steps: [
    {
      id: "s1",
      kind: "search",
      displayName: "Text (product name, notes, etc.)",
      searchName: "GenesByText",
      recordType: "transcript",
      parameters: {},
      isFiltered: false,
      estimatedSize: 45,
    },
  ],
  rootStepId: "s1",
  isSaved: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

const CHECKED = {
  complete: true,
  successful: true,
  caveats: [],
};

function view(overrides: Parameters<typeof makeLedger>[0] = {}): LedgerView | null {
  return readLedger(makeLedger(overrides));
}

function input(overrides: Partial<ReviewInput> = {}): ReviewInput {
  return {
    ledger: null,
    card: null,
    superseded: false,
    runningPhase: null,
    strategy: null,
    rootCount: null,
    ...overrides,
  };
}

function cardWith(drifted: number): EvidenceCard {
  return {
    ...EVIDENCE_CARD,
    steps: Array.from({ length: Math.max(drifted, 1) }, (_, i) => ({
      stepId: `s${i + 1}`,
      wdkStepId: 100 + i,
      title: `Step ${i + 1}`,
      recordedCount: 45,
      siteCount: drifted > 0 ? 46 : 45,
      drifted: drifted > 0,
    })),
  };
}

describe("reviewModel verdict", () => {
  it("working wins", () => {
    const model = reviewModel(
      input({ ledger: view({ verification: CHECKED }), runningPhase: "verification" }),
    );

    expect([model.verdict.kind, model.verdict.title]).toEqual([
      "working",
      `Working: ${phaseLabel("verification")}`,
    ]);
  });

  it("names a failed step by its display name", () => {
    const ledger = view({
      build: {
        ...makeLedger().build,
        succeeded: false,
        nodeResults: [
          {
            nodeId: "s1",
            searchName: "GenesByText",
            status: "failed",
            error: "Cannot INTERSECT steps with different organism scopes.",
          },
        ],
      },
    });

    const model = reviewModel(input({ ledger, strategy: STRATEGY }));

    expect(model.buildProblems).toEqual([
      {
        key: "s1",
        step: "Text (product name, notes, etc.)",
        status: "failed",
        sentence: "Cannot INTERSECT steps with different organism scopes.",
      },
    ]);
    expect(model.verdict.title).toBe("The build failed");
  });

  it("says a step returned nothing in the record type's words", () => {
    const ledger = view({
      build: {
        ...makeLedger().build,
        nodeResults: [{ nodeId: "s9", searchName: "__combine__", status: "zero" }],
      },
    });

    const model = reviewModel(input({ ledger, strategy: STRATEGY }));

    expect(model.buildProblems).toEqual([
      { key: "s9", step: "Combine", status: "zero", sentence: "Returned 0 results." },
    ]);
  });

  it("a superseded card wins over a passing check", () => {
    const model = reviewModel(
      input({
        ledger: view({ verification: CHECKED }),
        card: cardWith(0),
        superseded: true,
        strategy: STRATEGY,
      }),
    );

    expect([model.verdict.kind, model.verdict.title]).toEqual([
      "stale",
      "The strategy changed after the last check",
    ]);
  });

  it("counts a single gap", () => {
    const ledger = view({
      verification: {
        ...CHECKED,
        digest: {
          prose: "The check read the records.",
          gaps: [
            {
              kind: "requirement",
              text: "sporozoite expression",
              sentence: "Sporozoite expression has no search.",
            },
          ],
        },
      },
    });

    const model = reviewModel(input({ ledger, strategy: STRATEGY }));

    expect([model.verdict.tone, model.verdict.title]).toEqual([
      "warn",
      "1 part of your question not answered",
    ]);
    expect(model.caveats).toEqual(["Sporozoite expression has no search."]);
  });

  it("answered with matching counts", () => {
    const model = reviewModel(
      input({
        ledger: view({ verification: CHECKED }),
        card: cardWith(0),
        strategy: STRATEGY,
        rootCount: 45,
      }),
    );

    expect([model.verdict.tone, model.verdict.title, model.verdict.detail]).toEqual([
      "good",
      "The strategy answers your question",
      "45 genes · counts match the site",
    ]);
  });

  it("answered with drift", () => {
    const model = reviewModel(
      input({
        ledger: view({ verification: CHECKED }),
        card: cardWith(2),
        strategy: STRATEGY,
        rootCount: 45,
      }),
    );

    expect(model.verdict.detail).toBe("45 genes · 2 counts changed on the site");
  });

  it("answered when the site did not answer the check", () => {
    const model = reviewModel(
      input({
        ledger: view({ verification: CHECKED }),
        card: { ...cardWith(0), siteRead: "not_answered" },
        strategy: STRATEGY,
        rootCount: 45,
      }),
    );

    expect(model.verdict.detail).toBe("45 genes · the site did not answer");
  });

  it("states the live root count, not the stored one", () => {
    const model = reviewModel(
      input({
        ledger: view({ verification: CHECKED }),
        strategy: STRATEGY,
        rootCount: 46,
      }),
    );

    expect(model.verdict.detail).toBe("46 genes");
  });

  it("a check that did not pass gives its reason", () => {
    const ledger = view({
      verification: {
        complete: true,
        successful: false,
        digest: {
          prose: "The check read the records.",
          reason: "The controls were not returned.",
        },
      },
    });

    const model = reviewModel(input({ ledger, strategy: STRATEGY }));

    expect([model.verdict.tone, model.verdict.title, model.verdict.detail]).toEqual([
      "bad",
      "The check did not pass",
      "The controls were not returned.",
    ]);
  });

  it("a built strategy without a check", () => {
    const model = reviewModel(input({ ledger: view(), strategy: STRATEGY }));

    expect([model.verdict.kind, model.verdict.title]).toEqual([
      "unchecked",
      "Built, not checked yet",
    ]);
  });

  it("a question with nothing built yet", () => {
    const model = reviewModel(input({ ledger: view() }));

    expect([model.verdict.kind, model.verdict.title]).toEqual([
      "unbuilt",
      "Not built yet",
    ]);
  });

  it("empty state", () => {
    const model = reviewModel(input());

    expect([model.verdict.kind, model.verdict.title, model.verdict.detail]).toEqual([
      "empty",
      "Nothing to review yet",
      "Ask a question and its plan, build and check appear here.",
    ]);
  });
});

describe("reviewModel rows", () => {
  it("question falls back to the spec goal", () => {
    const ledger = view({
      userIntent: null,
      frame: {
        ...makeLedger().frame,
        spec: { interpretedGoal: "Transporters essential in Apicomplexa", goal: "x" },
      },
    });

    expect(reviewModel(input({ ledger })).question).toBe(
      "Transporters essential in Apicomplexa",
    );
  });

  it("maps requirement statuses", () => {
    const ledger = view({
      constraints: {
        grounded: [
          groundedEntry("scope", "grounded"),
          groundedEntry("data type", "substituted"),
          groundedEntry("phenotype", "ungroundable"),
          groundedEntry("stage", "not_verified"),
          groundedEntry("record type", "grounded", "assumed"),
        ],
        unmetCount: 1,
        blocking: false,
      },
    });

    const rows = reviewModel(input({ ledger })).requirements;

    expect(rows.map((row) => [row.label, row.status, row.note])).toEqual([
      ["scope", "met", null],
      ["data type", "different", "data type answered another way"],
      ["phenotype", "missed", null],
      ["stage", "unchecked", null],
    ]);
    expect(rows[0]?.requested).toBe("scope value");
  });

  it("splits choices from caveats", () => {
    const ledger = view({
      verification: {
        ...CHECKED,
        caveats: [
          {
            kind: "assumed_value",
            criterionId: "s1",
            paramDisplayName: "Text term",
            value: "transport*",
            source: "chosen",
            boundCount: 47668,
            readingKind: "wildcard_phrase",
            reading: "transport",
            readingCount: 12000,
            sentence: "Text term transport* was chosen for you.",
          },
          { kind: "controls", sentence: SAMPLE_CAVEAT_SENTENCE },
        ],
      },
    });

    const model = reviewModel(input({ ledger }));

    expect(model.choices).toEqual([
      {
        key: "s1:Text term",
        param: "Text term",
        value: "transport*",
        source: "chosen",
        sentence: "Text term transport* was chosen for you.",
      },
    ]);
    expect(model.caveats).toEqual([SAMPLE_CAVEAT_SENTENCE]);
  });

  it("counts the spot check by fit", () => {
    const card: EvidenceCard = {
      ...cardWith(0),
      review: {
        sampledGenes: [
          { geneId: "PKNH_0902400", fits: "yes", why: "a transporter" },
          { geneId: "PKNH_0304200", fits: "unclear", why: "a subunit" },
          { geneId: "PKNH_0507000", fits: "no", why: "coatomer" },
          { geneId: "PKNH_1147200", fits: "yes", why: "an antiporter" },
        ],
      },
    };

    const spot = reviewModel(input({ card })).spotCheck;

    expect([spot?.yes, spot?.unclear, spot?.no, spot?.genes.length]).toEqual([
      2, 1, 1, 4,
    ]);
  });
});
