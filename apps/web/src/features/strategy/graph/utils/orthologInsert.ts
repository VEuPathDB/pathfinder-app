import type { Search, Step } from "@pathfinder/shared";
import { resolveRecordType } from "@/features/strategy/graph";

type OrthologInsertResult = {
  newStep: Step;
  downstreamPatch?: { stepId: string; patch: Partial<Step> };
};

function findFirstDownstream(
  steps: Step[],
  selectedId: string,
): { step: Step; uses: "primary" | "secondary" } | null {
  for (const s of steps) {
    if (s.primaryInputStepId === selectedId) return { step: s, uses: "primary" };
    if (s.secondaryInputStepId === selectedId) return { step: s, uses: "secondary" };
  }
  return null;
}

export function computeOrthologInsert(args: {
  selectedId: string;
  steps: Step[];
  strategyRecordType?: string | null;
  search: Search;
  options: { insertBetween: boolean };
  generateId: () => string;
}): OrthologInsertResult {
  const { selectedId, steps, strategyRecordType, search, options, generateId } = args;
  const stepsById = new Map(steps.map((s) => [s.id, s]));

  const inferredRecordType =
    resolveRecordType(selectedId, stepsById) ??
    strategyRecordType ??
    stepsById.get(selectedId)?.recordType ??
    null;

  const newId = generateId();
  const newStep: Step = {
    id: newId,
    kind: "transform",
    displayName: search.displayName || "Find orthologs",
    searchName: search.name,
    recordType: inferredRecordType,
    parameters: {},
    primaryInputStepId: selectedId,
    isFiltered: false,
  };

  const downstream = findFirstDownstream(steps, selectedId);
  if (!options.insertBetween || !downstream) {
    return { newStep };
  }

  if (downstream.uses === "primary") {
    return {
      newStep,
      downstreamPatch: {
        stepId: downstream.step.id,
        patch: { primaryInputStepId: newId },
      },
    };
  }
  return {
    newStep,
    downstreamPatch: {
      stepId: downstream.step.id,
      patch: { secondaryInputStepId: newId },
    },
  };
}
