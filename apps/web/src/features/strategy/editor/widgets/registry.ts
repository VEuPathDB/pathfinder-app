/**
 * Widget registry - maps WDK displayType (and spec.type) to React components.
 *
 * Dispatch order:
 * 1. Composite widgets claim groups of params (e.g., PhyleticProfile).
 * 2. Unclaimed visible params route by displayType first, then spec.type.
 * 3. Hidden unclaimed params -> skip rendering, collect defaults.
 */

import type { ParamSpec } from "@/features/strategy/parameters/spec";

/** Resolve the canonical displayType string from a param spec. */
function resolveDisplayType(spec: ParamSpec): string {
  return (spec.displayType ?? "").trim().toLowerCase();
}

/** Check if a param is hidden (should not render UI). */
export function isHiddenParam(spec: ParamSpec): boolean {
  return spec.isVisible === false || spec.group === "_hidden";
}

/** Check if a param belongs to the "advancedParams" group. */
export function isAdvancedParam(spec: ParamSpec): boolean {
  return spec.group === "advancedParams";
}

/**
 * Canonical display type constants matching WDK's enum values (lowercased).
 * Empty string -> fall through to spec.type dispatch.
 */
const DISPLAY_TYPES = {
  TREE_BOX: "treebox",
  TYPE_AHEAD: "typeahead",
  SELECT: "select",
  CHECK_BOX: "checkbox",
  STRING: "",
} as const;

export type WidgetKind =
  | "treebox"
  | "typeahead"
  | "select"
  | "checkbox"
  | "string"
  | "number"
  | "date"
  | "number-range"
  | "date-range"
  | "timestamp"
  | "filter"
  | "dataset"
  | "input-step";

/** Resolve which widget should render this spec. */
export function resolveWidgetKind(spec: ParamSpec): WidgetKind {
  const displayType = resolveDisplayType(spec);
  if (displayType === DISPLAY_TYPES.TREE_BOX) return "treebox";
  if (displayType === DISPLAY_TYPES.TYPE_AHEAD) return "typeahead";
  if (displayType === DISPLAY_TYPES.SELECT) return "select";
  if (displayType === DISPLAY_TYPES.CHECK_BOX) return "checkbox";

  const type = spec.type.trim().toLowerCase();
  if (type === "string") return "string";
  if (type === "number") return "number";
  if (type === "date") return "date";
  if (type === "number-range") return "number-range";
  if (type === "date-range") return "date-range";
  if (type === "timestamp") return "timestamp";
  if (type === "filter") return "filter";
  if (type === "input-dataset") return "dataset";
  if (type === "input-step") return "input-step";
  return "string";
}
