"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils/cn";
import { isMultiParam } from "@/features/strategy/parameters/spec";
import type { ParamWidgetProps } from "./types";

export function CheckboxParam({
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
        <RadioGroup
          value={value}
          onValueChange={(next) => field.handleChange(next)}
          disabled={disabled}
          aria-invalid={hasError ? "true" : undefined}
          aria-describedby={hasError ? `${name}-error` : undefined}
          className={cn(
            "rounded-md border bg-card p-2 space-y-1",
            hasError ? "border-destructive/30 bg-destructive/5" : "border-border",
          )}
        >
          {options.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 text-sm">
              <RadioGroupItem
                value={opt.value}
                aria-label={opt.label}
                onBlur={field.handleBlur}
              />
              {opt.label}
            </label>
          ))}
        </RadioGroup>
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

  const currentValue: string[] = Array.isArray(field.state.value)
    ? (field.state.value as unknown[]).filter((v): v is string => typeof v === "string")
    : [];
  const allSelected = options.length > 0 && currentValue.length === options.length;

  const toggleAll = () => {
    field.handleChange(allSelected ? [] : options.map((o) => o.value));
  };

  const toggle = (val: string) => {
    field.handleChange(
      currentValue.includes(val)
        ? currentValue.filter((v) => v !== val)
        : [...currentValue, val],
    );
  };

  return (
    <div>
      <fieldset
        aria-invalid={hasError ? "true" : undefined}
        aria-describedby={hasError ? `${name}-error` : undefined}
        className={cn(
          "rounded-md border bg-card max-h-48 overflow-y-auto p-2",
          hasError ? "border-destructive/30 bg-destructive/5" : "border-border",
        )}
      >
        {options.length > 3 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground mb-1 pb-1 border-b border-border">
            <Checkbox
              checked={allSelected}
              disabled={disabled}
              onCheckedChange={toggleAll}
              aria-label="Select all"
            />
            Select all ({options.length})
          </label>
        )}
        {options.map((opt) => (
          <label key={opt.value} className="flex items-center gap-2 text-sm py-0.5">
            <Checkbox
              checked={currentValue.includes(opt.value)}
              disabled={disabled}
              onCheckedChange={() => toggle(opt.value)}
              onBlur={field.handleBlur}
              aria-label={opt.label}
            />
            {opt.label}
          </label>
        ))}
      </fieldset>
      {hasError && errorMessage != null && (
        <p id={`${name}-error`} role="alert" className="mt-1 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
