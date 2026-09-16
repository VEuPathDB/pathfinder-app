export type { ParamSpec } from "@pathfinder/shared";

/** Narrow input for isMultiParam - accepts both full ParamSpec and partial test fixtures. */
interface MultiParamInput {
  allowMultipleValues?: boolean | null;
  multiPick?: boolean | null;
  maxSelectedCount?: number | null;
  type?: string;
}

export function isMultiParam(spec: MultiParamInput) {
  if (spec.allowMultipleValues === true || spec.multiPick === true) return true;
  if (typeof spec.maxSelectedCount === "number" && spec.maxSelectedCount > 1) {
    return true;
  }
  return (spec.type ?? "").toLowerCase().includes("multi");
}
