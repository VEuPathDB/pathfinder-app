import type { Step } from "@pathfinder/shared";

/**
 * Steps not reachable from `rootStepId` via primary/secondary input chains.
 * When `rootStepId` is null/empty, every step counts as an orphan (no anchor
 * to walk from).
 */
export function findOrphanSteps(steps: Step[], rootStepId: string | null): Step[] {
  if (steps.length === 0) return [];
  if (rootStepId == null || rootStepId === "") return steps;
  const byId = new Map(steps.map((s) => [s.id, s]));
  const reachable = new Set<string>();
  const stack: string[] = [rootStepId];
  while (stack.length > 0) {
    const id = stack.pop();
    if (id == null || reachable.has(id)) continue;
    reachable.add(id);
    const step = byId.get(id);
    if (!step) continue;
    if (step.primaryInputStepId != null && step.primaryInputStepId !== "") {
      stack.push(step.primaryInputStepId);
    }
    if (step.secondaryInputStepId != null && step.secondaryInputStepId !== "") {
      stack.push(step.secondaryInputStepId);
    }
  }
  return steps.filter((s) => !reachable.has(s.id));
}
