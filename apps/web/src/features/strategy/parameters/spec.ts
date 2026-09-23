export type { ParamSpec } from "@pathfinder/shared";

/** Narrow input for isMultiParam - accepts both full ParamSpec and partial test fixtures. */
interface MultiParamInput {
  allowMultipleValues?: boolean | null;
  multiPick?: boolean | null;
  maxSelectedCount?: number | null;
  type?: string;
}

/** A step's input wiring: the graph sets it, so no form shows it and no patch sends it. */
export function isInputStepParam(spec: { type?: string }): boolean {
  return spec.type === "input-step";
}

export function isMultiParam(spec: MultiParamInput) {
  if (spec.allowMultipleValues === true || spec.multiPick === true) return true;
  if (typeof spec.maxSelectedCount === "number" && spec.maxSelectedCount > 1) {
    return true;
  }
  return (spec.type ?? "").toLowerCase().includes("multi");
}
