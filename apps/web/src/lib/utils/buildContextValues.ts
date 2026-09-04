import type { StepParameters } from "@/lib/types/stepParameters";

export function buildContextValues(
  values: StepParameters,
  allowedKeys?: string[],
): StepParameters {
  const filtered: StepParameters = {};
  for (const [key, value] of Object.entries(values)) {
    if (allowedKeys && !allowedKeys.includes(key)) continue;
    if (value === "@@fake@@") continue;
    if (Array.isArray(value) && value.includes("@@fake@@")) continue;
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    filtered[key] = value;
  }
  return filtered;
}
