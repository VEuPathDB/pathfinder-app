import type { CombineOp, StrategyStepNode, StrategyAst } from "@pathfinder/shared";
import { DEFAULT_STREAM_NAME } from "@pathfinder/shared";
import type { Step, Strategy } from "@pathfinder/shared";
import { walkSubtreeIds } from "@/features/strategy/operations";

type ParamMap = NonNullable<Step["parameters"]>;

export type SerializedStrategyPlan = {
  plan: StrategyAst;
  name: string;
  recordType: string | null;
  /** Step IDs not reachable from the chosen root. Excluded from the pushed plan. */
  orphanIds: string[];
};

function sanitizeParametersForPlan(params: ParamMap): ParamMap {
  const next: ParamMap = {};
  for (const [key, value] of Object.entries(params)) {
    if (
      value.type === "multi-pick-vocabulary" &&
      (value.values ?? []).includes("@@fake@@")
    ) {
      continue;
    }
    if (value.type === "single-pick-vocabulary" && value.value === "@@fake@@") {
      continue;
    }
    next[key] = value;
  }
  return next;
}

export function serializeStrategyAst(
  stepsById: Record<string, Step>,
  strategy: Strategy | null,
): SerializedStrategyPlan | null {
  const steps = Object.values(stepsById);
  if (steps.length === 0) return null;

  const recordType = strategy?.recordType ?? steps[0]?.recordType ?? "gene";

  const inputStepIds = new Set<string>();
  for (const step of steps) {
    if (step.primaryInputStepId != null) inputStepIds.add(step.primaryInputStepId);
    if (step.secondaryInputStepId != null) inputStepIds.add(step.secondaryInputStepId);
  }
  const rootSteps = steps.filter((s) => !inputStepIds.has(s.id));
  // Choose the canonical root: prefer Strategy.rootStepId when it is still an
  // actual root (i.e. not consumed by another step). Otherwise fall back to the
  // unique root if there is exactly one. When neither resolves, the graph is
  // genuinely ambiguous (multi-root with no choice committed) and we refuse.
  // Tolerating stale rootStepId is critical because optimistic mutations append
  // a combine before the cache rootStepId is refreshed by the server response.
  let chosenRootId: string | null = null;
  if (
    strategy?.rootStepId != null &&
    strategy.rootStepId !== "" &&
    stepsById[strategy.rootStepId] !== undefined &&
    !inputStepIds.has(strategy.rootStepId)
  ) {
    chosenRootId = strategy.rootStepId;
  } else if (rootSteps.length === 1) {
    chosenRootId = rootSteps[0]!.id;
  }
  if (chosenRootId == null) return null;
  const rootStep = stepsById[chosenRootId]!;
  const reachable = new Set(walkSubtreeIds(steps, chosenRootId));
  const orphanIds = steps.filter((s) => !reachable.has(s.id)).map((s) => s.id);

  const buildNode = (stepId: string): StrategyStepNode | null => {
    const step = stepsById[stepId];
    if (!step) return null;

    const isCombine =
      step.primaryInputStepId != null && step.secondaryInputStepId != null;
    // Combine nodes don't have a user-selected searchName in the UI; use the backend's
    // placeholder. Combine steps are structural (primary+secondary+operator) and do not
    // require a real WDK question name.
    const resolvedSearchName =
      step.searchName != null && step.searchName !== ""
        ? step.searchName
        : isCombine
          ? "__combine__"
          : null;
    if (resolvedSearchName == null) return null;

    const node: StrategyStepNode = {
      id: step.id,
      searchName: resolvedSearchName,
      displayName: step.displayName ?? "",
      parameters: sanitizeParametersForPlan(step.parameters ?? {}),
    };

    if (step.primaryInputStepId != null) {
      const primary = buildNode(step.primaryInputStepId);
      if (!primary) return null;
      node.primaryInput = primary;
    }

    if (step.secondaryInputStepId != null) {
      // secondary implies primary for our plan contract
      if (step.primaryInputStepId == null) return null;
      const secondary = buildNode(step.secondaryInputStepId);
      if (!secondary) return null;
      node.secondaryInput = secondary;
      if (step.operator == null) return null;
      node.operator = step.operator as CombineOp;
      if (step.operator === "COLOCATE" && step.colocationParams) {
        node.colocationParams = step.colocationParams;
      }
    }

    return node;
  };

  const rootNode = buildNode(rootStep.id);
  if (!rootNode) return null;

  const name =
    strategy?.name != null && strategy.name !== ""
      ? strategy.name
      : DEFAULT_STREAM_NAME;
  return {
    name,
    recordType,
    orphanIds,
    plan: {
      recordType,
      root: rootNode,
      name,
      ...(strategy?.description != null ? { description: strategy.description } : {}),
    },
  };
}
