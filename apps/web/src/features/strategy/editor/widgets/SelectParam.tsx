"use client";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils/cn";
import { isMultiParam } from "@/features/strategy/parameters/spec";
import type { ParamWidgetProps } from "./types";

const PLACEHOLDER_VALUE = "__placeholder__";

export function SelectParam({
  spec,
  name,
  options,
  field,
  disabled = false,
}: ParamWidgetProps) {
  const multi = isMultiParam(spec);
  const errors = field.state.meta.errors;
  const hasError = errors.length > 0;
  const errorMessage = hasError ? String(errors[0]) : null;

  if (!multi) {
    const value = typeof field.state.value === "string" ? field.state.value : "";
    return (
      <div>
        <Select
          disabled={disabled}
          value={value === "" ? PLACEHOLDER_VALUE : value}
          onValueChange={(next) =>
            field.handleChange(next === PLACEHOLDER_VALUE ? "" : next)
          }
        >
          <SelectTrigger
            aria-invalid={hasError ? "true" : undefined}
            aria-describedby={hasError ? `${name}-error` : undefined}
            className="w-full"
            onBlur={field.handleBlur}
          >
            <SelectValue placeholder="-- Select --" />
          </SelectTrigger>
          <SelectContent>
            {spec.allowEmptyValue !== false && (
              <SelectItem value={PLACEHOLDER_VALUE}>-- Select --</SelectItem>
            )}
            {options.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasError && errorMessage != null && (
          <p
            id={`${name}-error`}
            role="alert"
            className="mt-1 text-xs text-destructive"
          >
            {errorMessage}
          </p>
        )}
      </div>
    );
  }

  const selected: string[] = Array.isArray(field.state.value) ? field.state.value : [];
  const allSelected = options.length > 0 && selected.length === options.length;

  const toggleAll = () => {
    field.handleChange(allSelected ? [] : options.map((o) => o.value));
  };

  const toggle = (val: string) => {
    field.handleChange(
      selected.includes(val) ? selected.filter((v) => v !== val) : [...selected, val],
    );
  };

  return (
    <div>
      <div
        aria-invalid={hasError ? "true" : undefined}
        className={cn(
          "rounded-md border bg-card max-h-48 overflow-y-auto p-2",
          hasError ? "border-destructive/30 bg-destructive/5" : "border-border",
        )}
      >
        {options.length > 3 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground mb-1 pb-1 border-b border-border">
            <Checkbox
              checked={allSelected}
              onCheckedChange={toggleAll}
              aria-label="Select all"
            />
            Select all ({options.length})
          </label>
        )}
        {options.map((opt) => (
          <label key={opt.value} className="flex items-center gap-2 text-sm py-0.5">
            <Checkbox
              checked={selected.includes(opt.value)}
              onCheckedChange={() => toggle(opt.value)}
              aria-label={opt.label}
            />
            {opt.label}
          </label>
        ))}
      </div>
      {hasError && errorMessage != null && (
        <p id={`${name}-error`} role="alert" className="mt-1 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
