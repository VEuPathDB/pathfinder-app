import { useId, useState } from "react";
import { useForm } from "@tanstack/react-form";
import type { ParamSpec } from "@pathfinder/shared";
import type { StepParameters } from "@/lib/types/stepParameters";
import { isInputStepParam, isMultiParam } from "@/features/strategy/parameters/spec";
import { paramValueToRaw } from "@/features/strategy/parameters/paramValue";
import type { ParamValue } from "@/lib/parameters/paramValue";

export type ParamFormValues = Record<string, string | string[]>;

/** A WDK initial display value as the multi-pick widget reads it. */
function coerceToMulti(raw: string | null | undefined): string[] {
  if (raw == null) return [];
  if (raw.startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      /* a value that is not JSON is one plain term */
    }
  }
  return raw.length > 0 ? [raw] : [];
}

function coerceToSingle(raw: string | null | undefined): string {
  return raw ?? "";
}

/**
 * Form values from the persisted parameters, and from the WDK initial display
 * value for a parameter the step does not carry. A persisted value goes
 * through the converter that save and change detection also use.
 */
function extractDefaults(
  specs: ParamSpec[],
  override?: StepParameters,
): ParamFormValues {
  const defaults: ParamFormValues = {};
  for (const spec of specs) {
    if (spec.name === "" || spec.isVisible === false || isInputStepParam(spec))
      continue;
    const persisted: ParamValue | undefined = override?.[spec.name];
    if (persisted !== undefined) {
      defaults[spec.name] = paramValueToRaw(persisted);
      continue;
    }
    const raw = spec.initialDisplayValue;
    defaults[spec.name] = isMultiParam(spec) ? coerceToMulti(raw) : coerceToSingle(raw);
  }
  return defaults;
}

export { extractDefaults };

function useParamFormInternal(
  formId: string,
  specs: ParamSpec[],
  override?: StepParameters,
) {
  return useForm({
    formId,
    defaultValues: extractDefaults(specs, override),
    onSubmit: () => {
      // submission handled externally via mutations
    },
  });
}

export type ParamForm = ReturnType<typeof useParamFormInternal>;

export interface UseParamFormResult {
  form: ParamForm;
  /**
   * `true` once the form has reset to defaults built from the current
   * `(specs, override)` inputs. `false` on initial mount when `specs` is empty
   * (defaults map is `{}` and contains nothing meaningful to save). Consumers
   * gate autosave on this so user edits are not overwritten by stale form
   * state, and so the WDK defaults shown briefly before saved values arrive
   * are not autosaved back over the user's actual values.
   */
  hydrated: boolean;
}

/**
 * Form bound to the current `paramSpecs`. When `paramSpecs` identity OR the
 * `override` identity changes (e.g. user picks a different searchName, or a
 * step's persisted `parameters` arrive), the form is REPLACED with a fresh
 * instance seeded from the new defaults, by rotating `formId` via the
 * render-time prevValue pattern. `useForm` swaps in a new `FormApi` when
 * `formId` changes, so no external store is written during render - a
 * render-phase `form.reset()` here would notify subscribers mid-render
 * ("Cannot update a component while rendering a different component").
 */
export function useParamForm(
  specs: ParamSpec[],
  override?: StepParameters,
): UseParamFormResult {
  const idPrefix = useId();
  const [prevSpecs, setPrevSpecs] = useState(specs);
  const [prevOverride, setPrevOverride] = useState(override);
  const [generation, setGeneration] = useState(0);

  if (specs !== prevSpecs || override !== prevOverride) {
    setPrevSpecs(specs);
    setPrevOverride(override);
    setGeneration(generation + 1);
  }

  const form = useParamFormInternal(`${idPrefix}${generation}`, specs, override);
  return { form, hydrated: specs.length > 0 };
}
