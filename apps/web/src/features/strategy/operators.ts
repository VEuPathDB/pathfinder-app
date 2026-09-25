import {
  COMBINE_OP_LABELS,
  combineOpEnum,
  type CombineOp,
  type Step,
} from "@pathfinder/shared";
import { DEFAULT_COLOCATION } from "./editor/schema/colocationSchema";

/** The labels an earlier release gave, which a stored combine may still carry. */
export const RETIRED_OPERATOR_LABELS: readonly string[] = [
  "Minus (reversed)",
  "Colocated",
];

const LABELS: ReadonlySet<string> = new Set([
  ...Object.values(COMBINE_OP_LABELS),
  ...RETIRED_OPERATOR_LABELS,
]);

function isCombineOp(operator: string): operator is CombineOp {
  return Object.hasOwn(COMBINE_OP_LABELS, operator);
}

export function operatorLabel(operator: string): string {
  return isCombineOp(operator) ? COMBINE_OP_LABELS[operator] : operator;
}

/** Whether a name is an operator's label, now or before, and not a researcher's. */
export function isOperatorLabel(name: string): boolean {
  return LABELS.has(name);
}

/**
 * The operators a researcher picks from: the four the site's own menu offers,
 * in its order, then Colocate. The site offers no menu entry for LONLY or RONLY.
 */
export const OFFERED_OPERATORS: readonly CombineOp[] = [
  combineOpEnum.INTERSECT,
  combineOpEnum.UNION,
  combineOpEnum.MINUS,
  combineOpEnum.RMINUS,
  combineOpEnum.COLOCATE,
];

/** The step change that sets an operator. Colocate needs its span parameters. */
export function operatorPatch(
  operator: CombineOp,
): Pick<Step, "operator"> & Partial<Pick<Step, "colocationParams">> {
  return operator === combineOpEnum.COLOCATE
    ? { operator, colocationParams: DEFAULT_COLOCATION }
    : { operator };
}
