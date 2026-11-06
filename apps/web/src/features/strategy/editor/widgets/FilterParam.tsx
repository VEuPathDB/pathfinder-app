"use client";

import { useState } from "react";
import { CodeIcon, ListIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";
import type { ParamWidgetProps } from "./types";
import {
  EMPTY_FILTER_VALUE,
  decodeFilterValue,
  encodeFilterValue,
  tryFormatJson,
  type FilterValueObject,
} from "./filterParamLogic";
import { FilterJsonEditor, FilterList } from "./FilterParamSubcomponents";

export function FilterParam({ spec, name, field }: ParamWidgetProps) {
  const raw = typeof field.state.value === "string" ? field.state.value : "";
  const decoded = decodeFilterValue(raw);
  const filters = decoded.parsed.filters;

  const [editingJson, setEditingJson] = useState(false);

  const errors = field.state.meta.errors;
  const hasError = errors.length > 0;
  const errorMessage = hasError ? String(errors[0]) : null;

  const commit = (next: FilterValueObject) => {
    field.handleChange(encodeFilterValue(next));
    field.handleBlur();
  };

  const removeAt = (index: number) => {
    commit({ filters: filters.filter((_, idx) => idx !== index) });
  };

  const clearAll = () => {
    commit(EMPTY_FILTER_VALUE);
  };

  const ontologyHint =
    spec.vocabulary === undefined || spec.vocabulary === null
      ? "Backend has not surfaced ontology metadata for this filter parameter; use the JSON editor."
      : null;

  return (
    <div
      data-testid="filter-param-root"
      data-invalid={hasError ? "true" : undefined}
      className={cn(
        "space-y-2 rounded-md border bg-card p-3",
        hasError ? "border-destructive/30 bg-destructive/5" : "border-border",
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ListIcon className="size-3.5" aria-hidden />
          <span>
            {filters.length === 1
              ? "1 active filter"
              : `${String(filters.length)} active filters`}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={() => setEditingJson((prev) => !prev)}
          >
            <CodeIcon className="size-3" aria-hidden />
            {editingJson ? "Hide JSON" : "Edit JSON"}
          </Button>
          {filters.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={clearAll}
            >
              Clear all
            </Button>
          )}
        </div>
      </div>

      {!decoded.ok && raw !== "" && (
        <p className="text-xs text-warning">
          Existing value is not a recognized filter shape. Use Edit JSON to inspect.
        </p>
      )}

      {!editingJson && <FilterList filters={filters} onRemove={removeAt} />}

      {editingJson && (
        <FilterJsonEditor
          name={name}
          initialJson={
            raw === ""
              ? JSON.stringify(EMPTY_FILTER_VALUE, null, 2)
              : tryFormatJson(raw)
          }
          onApply={(parsed) => {
            commit(parsed);
            setEditingJson(false);
          }}
          onCancel={() => setEditingJson(false)}
        />
      )}

      {ontologyHint !== null && !editingJson && (
        <p className="text-[0.6875rem] text-muted-foreground">{ontologyHint}</p>
      )}

      {hasError && errorMessage !== null && (
        <p id={`${name}-error`} role="alert" className="text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
