"use client";

import { Input } from "@/components/ui/input";
import type { ParamWidgetProps } from "./types";
import {
  decodeRange,
  encodeRange,
  type RangeParts,
} from "@/features/strategy/parameters/rangeCodec";

function specMin(spec: ParamWidgetProps["spec"]): string | undefined {
  if (typeof spec.min === "number") return String(spec.min);
  return undefined;
}
function specMax(spec: ParamWidgetProps["spec"]): string | undefined {
  if (typeof spec.max === "number") return String(spec.max);
  return undefined;
}

export function DateRangeParam({ spec, name, field }: ParamWidgetProps) {
  const value = typeof field.state.value === "string" ? field.state.value : "";
  const parts = decodeRange(value);

  const errors = field.state.meta.errors;
  const hasError = errors.length > 0;
  const errorMessage = hasError ? String(errors[0]) : null;

  const update = (next: RangeParts) => {
    field.handleChange(encodeRange(next.min, next.max));
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        <Input
          name={`${name}-min`}
          type="date"
          aria-label={`${name} min`}
          value={parts.min}
          onChange={(event) => update({ ...parts, min: event.target.value })}
          onBlur={field.handleBlur}
          min={specMin(spec)}
          max={specMax(spec)}
          aria-invalid={hasError ? "true" : undefined}
        />
        <span className="text-muted-foreground" aria-hidden>
          -
        </span>
        <Input
          name={`${name}-max`}
          type="date"
          aria-label={`${name} max`}
          value={parts.max}
          onChange={(event) => update({ ...parts, max: event.target.value })}
          onBlur={field.handleBlur}
          min={specMin(spec)}
          max={specMax(spec)}
          aria-invalid={hasError ? "true" : undefined}
        />
      </div>
      {hasError && errorMessage != null && (
        <p id={`${name}-error`} role="alert" className="mt-1 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
