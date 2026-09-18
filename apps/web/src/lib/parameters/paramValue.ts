import type { Step } from "@pathfinder/shared";

/** One typed WDK parameter value, as the wire declares it. */
export type ParamValue = NonNullable<Step["parameters"]>[string];
export type ParamValueMap = NonNullable<Step["parameters"]>;

function formatRange(min: string | null, max: string | null): string {
  if (min !== null && max !== null) return `${min} to ${max}`;
  if (min !== null) return `${min} or more`;
  if (max !== null) return `${max} or less`;
  return "(any)";
}

/** A typed parameter value as a researcher reads it. */
export function formatParamValue(value: ParamValue): string {
  switch (value.type) {
    case "string":
    case "date":
    case "timestamp":
    case "single-pick-vocabulary":
      return value.value;
    case "number":
      return String(value.value);
    case "multi-pick-vocabulary": {
      const values = value.values ?? [];
      return values.length === 0 ? "(none)" : values.join(", ");
    }
    case "number-range":
      return formatRange(
        value.min == null ? null : String(value.min),
        value.max == null ? null : String(value.max),
      );
    case "date-range":
      return formatRange(value.min ?? null, value.max ?? null);
    case "input-dataset":
      return value.datasetId;
    case "input-step":
      return value.stepId;
    case "filter": {
      const filters = value.filters ?? [];
      if (filters.length === 0) return "(no filters)";
      const fields = filters.map((f) => f.field).join(", ");
      return `${String(filters.length)} ${filters.length === 1 ? "filter" : "filters"} (${fields})`;
    }
  }
}

/** The vocabulary term the UI shows as "All". WDK refuses it as a submitted value. */
const ALL_TERM = "@@fake@@";

/** Whether a value carries the "All" vocabulary term. */
export function statesAllTerm(value: ParamValue): boolean {
  if (value.type === "single-pick-vocabulary") return value.value === ALL_TERM;
  if (value.type === "multi-pick-vocabulary") {
    return (value.values ?? []).includes(ALL_TERM);
  }
  return false;
}

/** Whether a value states no selection. A number of zero is a selection. */
export function statesNothing(value: ParamValue): boolean {
  switch (value.type) {
    case "string":
    case "date":
    case "timestamp":
    case "single-pick-vocabulary":
      return value.value === "";
    case "number":
      return false;
    case "multi-pick-vocabulary":
      return (value.values ?? []).length === 0;
    case "number-range":
    case "date-range":
      return value.min == null && value.max == null;
    case "input-dataset":
      return value.datasetId === "";
    case "input-step":
      return value.stepId === "";
    case "filter":
      return (value.filters ?? []).length === 0;
  }
}
