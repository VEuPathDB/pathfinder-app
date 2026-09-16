import { useId, useState } from "react";
import { useForm } from "@tanstack/react-form";
import type { ParamSpec } from "@pathfinder/shared";
import type { StepParameters } from "@/lib/types/stepParameters";
import { isMultiParam } from "@/features/strategy/parameters/spec";
import { paramValueToRaw } from "@/features/strategy/parameters/paramValue";
import type { ParamValue } from "@/lib/parameters/paramValue";

export type ParamFormValues = Record<string, string | string[]>;

function coerceToMulti(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(String);
  if (raw == null) return [];
  if (typeof raw === "string") {
    if (raw.startsWith("[")) {
      try {
        const parsed: unknown = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed.map(String);
      } catch {
        /* fall through to plain string handling */
      }
    }
    return raw.length > 0 ? [raw] : [];
  }
  return [String(raw)];
}

function coerceToSingle(raw: unknown): string {
  if (raw == null) return "";
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) return raw.length > 0 ? String(raw[0]) : "";
  return String(raw);
}

const PARAM_VALUE_TYPES: ReadonlySet<string> = new Set([
  "string",
  "date",
  "timestamp",
  "single-pick-vocabulary",
  "number",
  "multi-pick-vocabulary",
  "number-range",
  "date-range",
  "input-dataset",
  "input-step",
  "filter",
]);

/**
 * The persisted `step.parameters` map stores typed ``ParamValue`` objects
 * whose shape varies by ``type`` (``value`` / ``values`` / ``min``+``max`` /
 * ``filters`` / ``datasetId`` ...), NOT a uniform ``{type, value}``. Detect a
 * typed value so we can hand it to the canonical :func:`paramValueToRaw` -
 * the same converter ``buildStepPatch`` (save) and ``useStepDraftChanges``
 * (change detection) use, so the form loads identical raw values and reports
 * zero phantom changes. Ad-hoc coercion here previously rendered every typed
 * value as ``"[object Object]"`` (and trees as "0 selected").
 */
function asTypedParamValue(raw: unknown): ParamValue | null {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const type: unknown = (raw as { type?: unknown }).type;
  if (typeof type === "string" && PARAM_VALUE_TYPES.has(type)) {
    return raw as ParamValue;
  }
  return null;
}

function extractDefaults(
  specs: ParamSpec[],
  override?: StepParameters,
): ParamFormValues {
  const defaults: ParamFormValues = {};
  for (const spec of specs) {
    if (spec.name === "" || spec.isVisible === false) continue;
    const overrideHas =
      override !== undefined &&
      Object.prototype.hasOwnProperty.call(override, spec.name);
    const raw: unknown = overrideHas ? override[spec.name] : spec.initialDisplayValue;
    const typed = asTypedParamValue(raw);
    if (typed !== null) {
      // Typed persisted value (any param type) -> canonical raw form value.
      defaults[spec.name] = paramValueToRaw(typed);
      continue;
    }
    // Raw source (a WDK ``initialDisplayValue`` string, or an already-raw
    // override) -> the existing string/array coercion.
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
