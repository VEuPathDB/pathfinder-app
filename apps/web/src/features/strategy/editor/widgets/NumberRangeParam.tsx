"use client";

import { Input } from "@/components/ui/input";
import type { ParamWidgetProps } from "./types";
import {
  decodeRange,
  encodeRange,
  type RangeParts,
} from "@/features/strategy/parameters/rangeCodec";

export function NumberRangeParam({ spec, name, field }: ParamWidgetProps) {
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
          type="number"
          aria-label={`${name} min`}
          value={parts.min}
          onChange={(event) => update({ ...parts, min: event.target.value })}
          onBlur={field.handleBlur}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.increment ?? undefined}
          aria-invalid={hasError ? "true" : undefined}
        />
        <span className="text-muted-foreground" aria-hidden>
          -
        </span>
        <Input
          name={`${name}-max`}
          type="number"
          aria-label={`${name} max`}
          value={parts.max}
          onChange={(event) => update({ ...parts, max: event.target.value })}
          onBlur={field.handleBlur}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.increment ?? undefined}
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
