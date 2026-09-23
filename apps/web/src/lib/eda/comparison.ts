import type { EdaComparison } from "@pathfinder/shared/generated/types/EdaComparison";

/** The two groups one compute compares, in words. */
export function comparisonLine(comparison: EdaComparison): string {
  return `Group A: ${comparison.groupA.join(", ")} - Group B: ${comparison.groupB.join(", ")}`;
}

/** The side of the volcano one group's genes sit on, named by its labels. A
 * positive effect size is higher in group B. */
export function higherIn(
  comparison: EdaComparison | null | undefined,
  group: "A" | "B",
): string {
  if (comparison == null) return `Higher in group ${group}`;
  const labels = group === "A" ? comparison.groupA : comparison.groupB;
  return `Higher in ${labels.join(", ")}`;
}
