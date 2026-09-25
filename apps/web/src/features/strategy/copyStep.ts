import type { StepKind } from "@pathfinder/shared";

/**
 * A strategy is one tree, so a copy of a step joins the tree through an
 * intersect with its original. The action says so.
 */
export const COPY_STEP_ACTION = {
  label: "Intersect with a copy",
  title:
    "Adds a copy of this step and intersects it with the original, so the copy's parameters can be changed.",
} as const;

/** Only a search step has a copy: a copy of a combine or a transform has no inputs. */
export function hasACopy(kind: StepKind): boolean {
  return kind === "search";
}
