import type { EvidenceCard } from "@pathfinder/shared";

/** A card as `data-evidence-card` carries it: a two-kind control test on the
 * root step of a one-step plasmodb strategy that the site now counts higher. */
export const EVIDENCE_CARD: EvidenceCard = {
  checkId: "call_verify_1",
  revision: "rev-1",
  siteId: "plasmodb",
  checkedAt: "2026-09-24T09:30:00Z",
  wdkStrategyId: 300125410,
  strategyUrl:
    "https://plasmodb.org/plasmo/app/workspace/strategies/300125410/440299573",
  siteRead: "read",
  steps: [
    {
      stepId: "s1",
      wdkStepId: 440299573,
      title: "Genes by Molecular Weight",
      recordedCount: 1843,
      siteCount: 1851,
      drifted: true,
    },
  ],
  controls: [
    {
      testedLabel: "Genes by Molecular Weight",
      wdkStepId: 440299573,
      positive: {
        returned: ["PF3D7_0102600", "PF3D7_0709000"],
        notReturned: ["PF3D7_1133400"],
        controlsCount: 3,
        returnedCount: 2,
        rate: 2 / 3,
      },
      negative: {
        returned: [],
        notReturned: ["TGME49_205250", "PF3D7_1222600"],
        controlsCount: 2,
        returnedCount: 0,
        rate: 0,
      },
      enrichment: {
        population: 5,
        positives: 3,
        returned: 2,
        positivesReturned: 2,
        pValue: 0.3,
      },
    },
  ],
  citations: [
    {
      criterionId: "c1",
      criterionText: "genes of 10 to 20 kDa",
      references: ["https://doi.org/10.1038/nature12970"],
    },
  ],
  verdict: { supported: true, pendingChecks: [], refusedBecause: null },
};
