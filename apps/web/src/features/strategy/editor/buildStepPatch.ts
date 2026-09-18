import type { ColocationParams, Step } from "@pathfinder/shared";
import type { ParamSpec } from "@/features/strategy/parameters/spec";
import {
  paramValueToRaw,
  rawToParamValue,
} from "@/features/strategy/parameters/paramValue";
import type { ParamValueMap } from "@/lib/parameters/paramValue";
import type { ParamFormValues } from "./hooks/useParamForm";

export interface BuildPatchArgs {
  step: Step;
  formValues: ParamFormValues;
  hiddenDefaults: ParamFormValues;
  allowedParamKeys: ReadonlySet<string>;
  paramSpecs: ParamSpec[];
  operator: string;
  displayName: string;
  colocationParams: ColocationParams | null;
}

function rawEquals(a: string | string[], b: string | string[]): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((v, i) => v === b[i]);
  }
  if (Array.isArray(a) || Array.isArray(b)) return false;
  return a === b;
}

export function buildStepPatch(args: BuildPatchArgs): Partial<Step> {
  const baseParams = args.step.parameters ?? {};
  const specsByName = new Map(args.paramSpecs.map((s) => [s.name, s]));
  const parameters: ParamValueMap = {};

  const collect = (key: string, raw: string | string[]): void => {
    const spec = specsByName.get(key);
    if (spec === undefined) return;
    const baseTyped = baseParams[key];
    const baseRaw = baseTyped === undefined ? null : paramValueToRaw(baseTyped);
    if (baseRaw !== null && rawEquals(raw, baseRaw)) return;
    parameters[key] = rawToParamValue(spec, raw);
  };

  for (const [key, val] of Object.entries(args.formValues)) {
    if (!args.allowedParamKeys.has(key)) continue;
    collect(key, val);
  }
  for (const [key, val] of Object.entries(args.hiddenDefaults)) {
    collect(key, val);
  }

  const patch: Partial<Step> = {};
  if (Object.keys(parameters).length > 0) {
    patch.parameters = parameters;
  }
  if (args.operator !== (args.step.operator ?? "")) {
    patch.operator = args.operator;
  }
  if (args.displayName !== (args.step.displayName ?? "")) {
    patch.displayName = args.displayName;
  }
  const baseColocation = args.step.colocationParams ?? null;
  if (
    JSON.stringify(args.colocationParams ?? null) !== JSON.stringify(baseColocation)
  ) {
    patch.colocationParams = args.colocationParams;
  }
  return patch;
}
