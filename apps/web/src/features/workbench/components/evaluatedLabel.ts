import type { Experiment } from "@pathfinder/shared";

const DAY = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

/**
 * What the set's header says about the evaluation it holds.
 *
 * A run that reports no finish is dated by its start, and one that carries no
 * readable time is still announced.
 */
export function evaluatedLabel(experiment: Experiment | null): string | null {
  if (experiment === null) return null;
  const ran = new Date(experiment.completedAt ?? experiment.createdAt ?? "");
  if (Number.isNaN(ran.getTime())) return "Evaluated";
  return `Evaluated ${DAY.format(ran)}`;
}
