"use client";

import type { ColocationParams, Step } from "@strategist/shared";
import { paramValueToRaw } from "@/features/strategy/parameters/paramValue";

export interface StepDraftSnapshot {
  parameters: Record<string, string | string[]>;
  operator: string;
  displayName: string;
  colocationParams: ColocationParams | null;
}

export interface StepDraftChanges {
  changeCount: number;
  changedKeys: string[];
  hasChanges: boolean;
}

function normalizeStepBaseline(step: Step): StepDraftSnapshot {
  const baseParams: Record<string, string | string[]> = {};
  const stepParams = step.parameters ?? {};
  for (const [key, val] of Object.entries(stepParams)) {
    baseParams[key] = paramValueToRaw(val);
  }
  return {
    parameters: baseParams,
    operator: step.operator ?? "",
    displayName: step.displayName ?? "",
    colocationParams: step.colocationParams ?? null,
  };
}

function normalizeFormValue(value: unknown): string | string[] {
  if (Array.isArray(value)) return value.map(String);
  if (value == null) return "";
  return String(value);
}

function valuesEqual(
  a: string | string[] | undefined,
  b: string | string[] | undefined,
): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }
  if (a === undefined || b === undefined) {
    return (a ?? "") === (b ?? "");
  }
  return false;
}

function colocationEqual(
  a: ColocationParams | null,
  b: ColocationParams | null,
): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

export function useStepDraftChanges(args: {
  step: Step;
  formValues: Record<string, unknown>;
  operator: string;
  displayName: string;
  colocationParams: ColocationParams | null;
  allowedParamKeys: ReadonlySet<string>;
}): StepDraftChanges {
  const baseline = normalizeStepBaseline(args.step);
  const changedKeys: string[] = [];

  const seen = new Set<string>();
  for (const [key, raw] of Object.entries(args.formValues)) {
    if (!args.allowedParamKeys.has(key)) continue;
    seen.add(key);
    const next = normalizeFormValue(raw);
    if (!valuesEqual(baseline.parameters[key], next)) {
      changedKeys.push(`parameters.${key}`);
    }
  }
  for (const key of Object.keys(baseline.parameters)) {
    if (!args.allowedParamKeys.has(key)) continue;
    if (seen.has(key)) continue;
    changedKeys.push(`parameters.${key}`);
  }

  if (args.operator !== baseline.operator) changedKeys.push("operator");
  if (args.displayName !== baseline.displayName) changedKeys.push("displayName");
  if (!colocationEqual(args.colocationParams, baseline.colocationParams)) {
    changedKeys.push("colocationParams");
  }

  return {
    changeCount: changedKeys.length,
    changedKeys,
    hasChanges: changedKeys.length > 0,
  };
}
