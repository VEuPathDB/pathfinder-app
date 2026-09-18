import { statesAllTerm, statesNothing } from "@/lib/parameters/paramValue";
import type { StepParameters } from "@/lib/types/stepParameters";

/**
 * The parameter values WDK reads as context. A value that states nothing, and
 * a value that carries the "All" term, tell WDK nothing and are left out.
 */
export function buildContextValues(
  values: StepParameters,
  allowedKeys?: string[],
): StepParameters {
  const filtered: StepParameters = {};
  for (const [key, value] of Object.entries(values)) {
    if (allowedKeys && !allowedKeys.includes(key)) continue;
    if (statesAllTerm(value) || statesNothing(value)) continue;
    filtered[key] = value;
  }
  return filtered;
}
