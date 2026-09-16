import { z } from "zod";

const FilterValueSchema = z.union([
  z.array(z.union([z.string(), z.null(), z.number()])),
  z.object({
    min: z.union([z.number(), z.string(), z.null()]).optional(),
    max: z.union([z.number(), z.string(), z.null()]).optional(),
  }),
  z.string(),
  z.null(),
]);

export const FilterEntrySchema = z.object({
  field: z.string(),
  type: z.enum(["string", "number", "date", "longitude", "multiFilter"]).optional(),
  isRange: z.boolean().optional(),
  includeUnknown: z.boolean().optional(),
  value: FilterValueSchema.optional(),
});

export const FilterValueObjectSchema = z.object({
  filters: z.array(FilterEntrySchema).default([]),
});

export type FilterEntry = z.infer<typeof FilterEntrySchema>;
export type FilterValueObject = z.infer<typeof FilterValueObjectSchema>;

export const EMPTY_FILTER_VALUE: FilterValueObject = { filters: [] };

export interface DecodedFilterValue {
  parsed: FilterValueObject;
  ok: boolean;
}

export function decodeFilterValue(raw: string): DecodedFilterValue {
  if (!raw) return { parsed: EMPTY_FILTER_VALUE, ok: true };
  try {
    const json = JSON.parse(raw) as unknown;
    const result = FilterValueObjectSchema.safeParse(json);
    if (result.success) return { parsed: result.data, ok: true };
    if (Array.isArray(json)) {
      const arrResult = z.array(FilterEntrySchema).safeParse(json);
      if (arrResult.success) return { parsed: { filters: arrResult.data }, ok: true };
    }
    return { parsed: EMPTY_FILTER_VALUE, ok: false };
  } catch {
    return { parsed: EMPTY_FILTER_VALUE, ok: false };
  }
}

export function encodeFilterValue(value: FilterValueObject): string {
  if (value.filters.length === 0) return "";
  return JSON.stringify(value);
}

export function summarizeFilterValue(filter: FilterEntry): string {
  const value = filter.value;
  if (value === null || value === undefined) return "(any)";
  if (Array.isArray(value)) {
    if (value.length === 0) return "(empty)";
    const labels = value.map((v) => (v === null ? "unknown" : String(v)));
    if (labels.length <= 3) return labels.join(", ");
    return `${labels.slice(0, 3).join(", ")} +${labels.length - 3} more`;
  }
  if (typeof value === "object") {
    const min = value.min ?? "−∞";
    const max = value.max ?? "+∞";
    return `${String(min)} - ${String(max)}`;
  }
  return String(value);
}

export function fieldTypeLabel(filter: FilterEntry): string {
  if (filter.type === undefined) return "filter";
  if (filter.isRange === true) return `${filter.type} range`;
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
