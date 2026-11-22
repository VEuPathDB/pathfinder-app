import { filterValueSchema } from "@strategist/shared/generated/zod/filterValueSchema";
import { isMultiParam, type ParamSpec } from "@/features/strategy/parameters/spec";
import {
  decodeRange,
  encodeRange,
  type RangeParts,
} from "@/features/strategy/parameters/rangeCodec";
import type { ParamValue } from "@/lib/parameters/paramValue";
import { AppError } from "@/lib/errors/AppError";

/** A typed value as its form field holds it; a held value is its raw text. */
export function paramValueToRaw(v: ParamValue, spec?: ParamSpec): string | string[] {
  switch (v.type) {
    case "string":
    case "timestamp":
    case "single-pick-vocabulary":
      return v.value;
    case "date":
      return v.value ?? "";
    case "number":
      return v.value === null ? "" : String(v.value);
    case "multi-pick-vocabulary":
      return v.values ?? [];
    case "number-range":
    case "date-range":
      return encodeRange(String(v.min ?? ""), String(v.max ?? ""));
    case "input-dataset":
      return v.datasetId;
    case "input-step":
      return v.stepId;
    case "filter":
      return v.empty === true ? "" : JSON.stringify({ filters: v.filters ?? [] });
    case "held":
      return spec !== undefined && isMultiParam(spec) ? termsOfWire(v.wire) : v.wire;
  }
}

function jsonOf(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function parseRange(raw: string | string[]): RangeParts {
  return decodeRange(typeof raw === "string" ? raw : "");
}

function toNumberOrNull(spec: ParamSpec, s: string): number | null {
  if (s === "") return null;
  const n = Number(s);
  if (!Number.isFinite(n)) {
    throw new AppError(`${spec.displayName ?? spec.name} takes a number, not "${s}"`);
  }
  return n;
}

function asString(raw: string | string[]): string {
  if (typeof raw === "string") return raw;
  return raw[0] ?? "";
}

function asStringArray(raw: string | string[]): string[] {
  if (Array.isArray(raw)) return raw;
  return raw === "" ? [] : [raw];
}

export function rawToParamValue(spec: ParamSpec, raw: string | string[]): ParamValue {
  switch (spec.type) {
    case "number":
      return { type: "number", value: toNumberOrNull(spec, asString(raw)) };
    case "number-range": {
      const { min, max } = parseRange(raw);
      return {
        type: "number-range",
        min: toNumberOrNull(spec, min),
        max: toNumberOrNull(spec, max),
      };
    }
    case "date":
      return { type: "date", value: asString(raw) || null };
    case "date-range": {
      const { min, max } = parseRange(raw);
      return {
        type: "date-range",
        min: min === "" ? null : min,
        max: max === "" ? null : max,
      };
    }
    case "timestamp":
      return { type: "timestamp", value: asString(raw) };
    case "single-pick-vocabulary":
      return { type: "single-pick-vocabulary", value: asString(raw) };
    case "multi-pick-vocabulary":
      return { type: "multi-pick-vocabulary", values: asStringArray(raw) };
    case "input-dataset":
      return { type: "input-dataset", datasetId: asString(raw) };
    case "input-step":
      return { type: "input-step", stepId: asString(raw) };
    case "filter": {
      const s = asString(raw);
      if (s === "") return { type: "filter", filters: [], empty: true };
      const read = filterValueSchema.safeParse(jsonOf(s));
      if (!read.success) {
        throw new AppError(
          `${spec.displayName ?? spec.name} holds a value the editor cannot read`,
        );
      }
      return { type: "filter", filters: read.data.filters ?? [] };
    }
    default:
      return { type: "string", value: asString(raw) };
  }
}

/** A wire value as the multi-pick widget reads it: a JSON list, else one term. */
export function termsOfWire(raw: string | null | undefined): string[] {
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
