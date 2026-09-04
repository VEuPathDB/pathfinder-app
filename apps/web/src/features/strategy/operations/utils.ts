import type { Step } from "@pathfinder/shared";

export interface GraphIndex {
  byId: Map<string, Step>;
  consumerOf: Map<string, { stepId: string; slot: "primary" | "secondary" }>;
}

export function buildIndex(steps: Step[]): GraphIndex {
  const byId = new Map<string, Step>();
  const consumerOf = new Map<
    string,
    { stepId: string; slot: "primary" | "secondary" }
  >();
  for (const s of steps) byId.set(s.id, s);
  for (const s of steps) {
    if (s.primaryInputStepId != null && s.primaryInputStepId !== "") {
      consumerOf.set(s.primaryInputStepId, { stepId: s.id, slot: "primary" });
    }
    if (s.secondaryInputStepId != null && s.secondaryInputStepId !== "") {
      consumerOf.set(s.secondaryInputStepId, { stepId: s.id, slot: "secondary" });
    }
  }
  return { byId, consumerOf };
}

export function findParent(
  steps: Step[],
  stepId: string,
): { parent: Step; slot: "primary" | "secondary" } | null {
  for (const s of steps) {
    if (s.primaryInputStepId === stepId) return { parent: s, slot: "primary" };
    if (s.secondaryInputStepId === stepId) return { parent: s, slot: "secondary" };
  }
  return null;
}

export function walkSubtreeIds(steps: Step[], rootId: string): string[] {
  const idx = buildIndex(steps);
  if (!idx.byId.has(rootId)) return [];
  const out = new Set<string>();
  const stack = [rootId];
  while (stack.length > 0) {
    const id = stack.pop()!;
    if (out.has(id)) continue;
    const s = idx.byId.get(id);
    if (!s) continue;
    out.add(id);
    if (s.primaryInputStepId != null && s.primaryInputStepId !== "")
      stack.push(s.primaryInputStepId);
    if (s.secondaryInputStepId != null && s.secondaryInputStepId !== "")
      stack.push(s.secondaryInputStepId);
  }
  return Array.from(out);
}
