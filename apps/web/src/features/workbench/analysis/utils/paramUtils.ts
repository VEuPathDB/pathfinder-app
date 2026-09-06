import type { ParamSpec } from "@pathfinder/shared";
import { extractVocabOptions } from "@/lib/utils/vocab";

export interface VocabEntry {
  value: string;
  display: string;
}

export function flattenVocab(vocab: unknown): VocabEntry[] {
  return extractVocabOptions(vocab).map((o) => ({
    value: o.value,
    display: o.label,
  }));
}

export function isOptimizable(spec: ParamSpec): boolean {
  if (spec.type === "input-step") return false;
  if (spec.type === "input-dataset") return false;
  if (spec.type === "filter") return false;
  return true;
}

export function isParamRequired(spec: ParamSpec): boolean {
  if (spec.allowEmptyValue === true) return false;
  // isReadOnly / isVisible are WDK raw fields not in the generated schema —
  // check them defensively via runtime property access.
  const raw = spec as Record<string, unknown>;
  if (raw["isReadOnly"] != null && raw["isReadOnly"] !== false) return false;
  if (raw["isVisible"] === false) return false;
  if (spec.type === "input-step") return false;
  return true;
}

export function isMultiPickParam(spec: ParamSpec): boolean {
  return spec.type === "multi-pick-vocabulary" || spec.multiPick === true;
}

export function isParamEmpty(
  spec: ParamSpec,
  value: string | null | undefined,
): boolean {
  if (value == null || value === "") return true;
  if (isMultiPickParam(spec) && value === "[]") return true;
  return false;
}

export function parseMultiPickInitial(spec: ParamSpec, raw: string): string {
  if (!isMultiPickParam(spec) || !raw.startsWith("[")) return raw;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.join(",");
  } catch {
    /* not valid JSON */
  }
  return raw;
}

export function resolveDisplayValue(value: string, spec?: ParamSpec | null): string {
  if (spec?.vocabulary == null) return value;
  const entries = flattenVocab(spec.vocabulary);
  const match = entries.find((e) => e.value === value);
  return match?.display ?? value;
}

export function isNumericParam(spec: ParamSpec): boolean {
  const t = spec.type.toLowerCase();
  if (t === "number" || t === "number-range" || t === "integer" || t === "float")
    return true;
  if (spec.isNumber === true) return true;
  return false;
}

export function buildDisplayMap(
  parameters: Record<string, string>,
  paramSpecs: ParamSpec[],
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const [key, value] of Object.entries(parameters)) {
    const spec = paramSpecs.find((s) => s.name === key);
    if (spec?.vocabulary == null) continue;
    const entries = flattenVocab(spec.vocabulary);
    if (isMultiPickParam(spec)) {
      const vals = value.split(",").filter(Boolean);
      const displays = vals
        .map((v) => entries.find((e) => e.value === v)?.display ?? v)
        .join(", ");
      if (displays !== value) map[key] = displays;
    } else {
      const match = entries.find((e) => e.value === value);
      if (match && match.display !== value) map[key] = match.display;
    }
  }
  return map;
}
