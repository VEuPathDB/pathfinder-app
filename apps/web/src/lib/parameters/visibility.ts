import type { ParamSpec } from "@strategist/shared";

export function isInputStepParam(spec: { type?: string }): boolean {
  return spec.type === "input-step";
}

export function isShown(spec: ParamSpec): boolean {
  return spec.name !== "" && spec.isVisible !== false && !isInputStepParam(spec);
}

export function isEditable(spec: ParamSpec): boolean {
  return isShown(spec) && spec.isReadOnly !== true;
}
