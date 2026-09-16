/**
 * compactLayout - turns a strategy into a tree for the compact step list.
 *
 * A step's inputs are its children, so the root sits on top and indentation
 * means containment.
 */

import type { Step, StepKind } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";

// Public types

export interface CompactStep {
  id: string;
  displayName: string;
  kind: StepKind;
  recordType?: string | null;
  operator?: string | null;
  /** 1-based index in the strategy execution order. */
  stepNumber: number;
  /** WDK strategy id this combine's secondary input was inserted from. */
  expandedStrategyId?: number | null;
  /** Display label for the collapsed saved-strategy reference. */
  expandedName?: string | null;
  /** Names of a combine's two inputs, primary first. */
  operandNames?: [string, string];
  /**
   * The wire step this row was built from. The count, the draft status and the
   * push error are read off it, so it travels whole rather than field by field.
   */
  source: Step;
}

/** One step and the steps that feed it. */
export interface TreeNode {
  step: CompactStep;
  children: TreeNode[];
}

// Helpers

const OPERATOR_SYMBOL: Record<string, string> = {
  INTERSECT: "∩",
  UNION: "∪",
  MINUS: "-",
  RMINUS: "-",
  COLOCATE: "near",
};

function inputIds(step: Step): string[] {
  return [step.primaryInputStepId, step.secondaryInputStepId].filter(
    (id): id is string => id != null && id !== "",
  );
}

/**
 * Names one side of a combine. A combine has no name of its own, so it is
 * described by its operator and collapses to an ellipsis past `depth`.
 */
function describeOperand(
  step: Step | undefined,
  byId: Map<string, Step>,
  depth: number,
): string {
  if (step == null) return "";
  if (inferStepKind(step) !== "combine") return step.displayName ?? "";
  if (depth <= 0) return "...";
  const symbol = OPERATOR_SYMBOL[step.operator ?? ""] ?? step.operator ?? "";
  const left = describeOperand(
    byId.get(step.primaryInputStepId ?? ""),
    byId,
    depth - 1,
  );
  const right = describeOperand(
    byId.get(step.secondaryInputStepId ?? ""),
    byId,
    depth - 1,
  );
  return `(${left} ${symbol} ${right})`;
}

function operandNames(
  step: Step,
  byId: Map<string, Step>,
): [string, string] | undefined {
  const primary = byId.get(step.primaryInputStepId ?? "");
  const secondary = byId.get(step.secondaryInputStepId ?? "");
  if (primary == null || secondary == null) return undefined;
  return [describeOperand(primary, byId, 1), describeOperand(secondary, byId, 1)];
}

function toCompact(
  step: Step,
  stepNumber: number,
  byId: Map<string, Step>,
): CompactStep {
  const compact: CompactStep = {
    id: step.id,
    displayName: step.displayName ?? "",
    kind: inferStepKind(step),
    stepNumber,
    source: step,
  };
  if (step.recordType != null) compact.recordType = step.recordType;
  if (step.operator != null) compact.operator = step.operator;
  if (step.expandedStrategyId != null)
    compact.expandedStrategyId = step.expandedStrategyId;
  if (step.expandedName != null) compact.expandedName = step.expandedName;
  if (compact.kind === "combine") {
    const names = operandNames(step, byId);
    if (names != null) compact.operandNames = names;
  }
  return compact;
}

// Tree builder

/**
 * Build the step tree from a step array + rootStepId.
 *
 * 1. Topologically sort to assign execution step numbers, leaves first.
 * 2. Expand from the root downwards, each step's inputs becoming its children.
 */
export function buildStrategyTree(
  steps: Step[],
  rootStepId: string | null,
): TreeNode[] {
  if (steps.length === 0 || rootStepId == null || rootStepId === "") return [];

  const byId = new Map(steps.map((s) => [s.id, s]));
  if (!byId.has(rootStepId)) return [];

  const visited = new Set<string>();
  const ordered: Step[] = [];

  function topo(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const step = byId.get(id);
    if (!step) return;
    for (const input of inputIds(step)) topo(input);
    ordered.push(step);
  }

  topo(rootStepId);

  const stepNumbers = new Map<string, number>();
  ordered.forEach((s, i) => stepNumbers.set(s.id, i + 1));

  // A cycle would make the expansion below run forever; `seen` keeps a
  // malformed graph rendering as a truncated tree instead of hanging the tab.
  function expand(id: string, seen: Set<string>): TreeNode | undefined {
    const step = byId.get(id);
    if (step == null || seen.has(id)) return undefined;
    seen.add(id);
    return {
      step: toCompact(step, stepNumbers.get(id) ?? 0, byId),
      children: inputIds(step)
        .map((input) => expand(input, seen))
        .filter((node): node is TreeNode => node !== undefined),
    };
  }

  const root = expand(rootStepId, new Set<string>());
  return root == null ? [] : [root];
}
