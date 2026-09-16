import type { Experiment, GeneSet } from "@pathfinder/shared";

/** Whether an evaluation still describes the set it belongs to. */
export type EvaluationCurrency = "current" | "superseded" | "unrecorded";

/** The evaluation a set holds, read against the membership the set holds now. */
export interface SetEvaluation {
  experiment: Experiment;
  currency: EvaluationCurrency;
  scoredGeneCount: number | null;
  setGeneCount: number;
}

const DAY = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const NEEDS_EVALUATION = "Requires a completed evaluation first";
const RE_EVALUATE = "Re-evaluate to use this panel.";

function currencyOf(experiment: Experiment, geneSet: GeneSet): EvaluationCurrency {
  const scored = experiment.geneSetMembership;
  if (scored == null) return "unrecorded";
  return scored.digest === geneSet.membershipDigest ? "current" : "superseded";
}

/**
 * Read one evaluation against the set it belongs to.
 *
 * Membership is compared by the digest the API issues for both sides, because
 * two sets of the same size are different sets.
 */
export function setEvaluation(
  experiment: Experiment | null,
  geneSet: GeneSet | undefined,
): SetEvaluation | null {
  if (experiment === null || geneSet === undefined) return null;
  return {
    experiment,
    currency: currencyOf(experiment, geneSet),
    scoredGeneCount: experiment.geneSetMembership?.geneCount ?? null,
    setGeneCount: geneSet.geneCount,
  };
}

function ranOn(experiment: Experiment): string {
  const ran = new Date(experiment.completedAt ?? experiment.createdAt ?? "");
  return Number.isNaN(ran.getTime()) ? "Evaluated" : `Evaluated ${DAY.format(ran)}`;
}

/** What the set's header says about the evaluation it holds. */
export function evaluatedLabel(evaluation: SetEvaluation | null): string | null {
  if (evaluation === null) return null;
  const day = ranOn(evaluation.experiment);
  if (evaluation.currency === "current") return day;
  if (evaluation.currency === "unrecorded") return `${day} (genes not recorded)`;
  return `${day} (scored ${evaluation.scoredGeneCount} genes, out of date)`;
}

/** Why a panel that needs a current evaluation stays shut, or null when it opens. */
export function evaluationBlock(evaluation: SetEvaluation | null): string | null {
  if (evaluation === null) return NEEDS_EVALUATION;
  if (evaluation.currency === "current") return null;
  if (evaluation.currency === "unrecorded") {
    return `The evaluation does not record which genes it scored. ${RE_EVALUATE}`;
  }
  return (
    `The evaluation scored ${evaluation.scoredGeneCount} genes and this set ` +
    `now holds ${evaluation.setGeneCount}. ${RE_EVALUATE}`
  );
}
