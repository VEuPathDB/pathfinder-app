"use client";

import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { isMultiParam } from "@/features/strategy/parameters/spec";
import type { ParamWidgetProps } from "./types";

function toOptions(opts: { value: string; label: string }[]): ComboboxOption[] {
  return opts.map((o) => ({ value: o.value, label: o.label }));
}

export function TypeAheadParam({
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

  const comboboxOptions = toOptions(options);

  const triggerClass = hasError ? { triggerClassName: "border-destructive/30" } : {};

  return (
    <div>
      {multi ? (
        <Combobox
          multiple
          options={comboboxOptions}
          value={Array.isArray(field.state.value) ? field.state.value : []}
          onChange={(next) => field.handleChange(next)}
          placeholder="Type to search..."
          emptyMessage="No matches"
          disabled={disabled}
          {...triggerClass}
        />
      ) : (
        <Combobox
          multiple={false}
          options={comboboxOptions}
          value={
            typeof field.state.value === "string" && field.state.value !== ""
              ? field.state.value
              : null
          }
          onChange={(next) => field.handleChange(next ?? "")}
          placeholder="Type to search..."
          emptyMessage="No matches"
          disabled={disabled}
          {...triggerClass}
        />
      )}
      {hasError && errorMessage != null && (
        <p id={`${name}-error`} role="alert" className="mt-1 text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
