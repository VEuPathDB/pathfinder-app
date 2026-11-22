import type { FilterValue } from "@strategist/shared/generated/types/FilterValue";
import { filterValueSchema } from "@strategist/shared/generated/zod/filterValueSchema";

export type FilterClause = NonNullable<FilterValue["filters"]>[number];
export type FilterClauses = Required<Pick<FilterValue, "filters">>;

export const EMPTY_FILTER_VALUE: FilterClauses = { filters: [] };

export interface DecodedFilterValue {
  parsed: FilterClauses;
  ok: boolean;
}

export function readFilterValue(json: unknown): FilterClauses | null {
  const result = filterValueSchema.safeParse(json);
  return result.success ? { filters: result.data.filters ?? [] } : null;
}

export function decodeFilterValue(raw: string): DecodedFilterValue {
  if (!raw) return { parsed: EMPTY_FILTER_VALUE, ok: true };
  try {
    const parsed = readFilterValue(JSON.parse(raw));
    return parsed === null
      ? { parsed: EMPTY_FILTER_VALUE, ok: false }
      : { parsed, ok: true };
  } catch {
    return { parsed: EMPTY_FILTER_VALUE, ok: false };
  }
}

export function encodeFilterValue(value: FilterClauses): string {
  return JSON.stringify({ filters: value.filters });
}

function members(labels: string[]): string {
  if (labels.length === 0) return "(empty)";
  if (labels.length <= 3) return labels.join(", ");
  return `${labels.slice(0, 3).join(", ")} +${String(labels.length - 3)} more`;
}

export function summarizeFilterValue(filter: FilterClause): string {
  if (filter.type === "multiFilter") {
    const count = filter.value.filters.length;
    return `${filter.value.operation} of ${String(count)} ${count === 1 ? "filter" : "filters"}`;
  }
  if (filter.isRange) {
    const min = filter.value.min ?? "-inf";
    const max = filter.value.max ?? "+inf";
    return `${String(min)} - ${String(max)}`;
  }
  return members(filter.value.map(String));
}

export function fieldTypeLabel(filter: FilterClause): string {
  if (filter.isRange) return `${filter.type} range`;
  if (filter.type === "multiFilter") return "compound";
  return filter.type;
}

export function tryFormatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}
