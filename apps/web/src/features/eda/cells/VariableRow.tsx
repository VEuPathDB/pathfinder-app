"use client";

import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";

import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { FilterEditor } from "./FilterEditor";

const HINT_VALUES = 3;

export interface VariableRowProps {
  variable: EdaVariableResponse;
  current: EdaFilter | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onApply: (filter: EdaFilter) => void;
}

/** One line of context under the variable name, from what the wire declares. */
function variableHint(variable: EdaVariableResponse): string {
  const vocabulary = variable.vocabulary;
  if (vocabulary.length > 0) {
    const total = variable.vocabularyTotal;
    return `${String(total)} values: ${vocabulary.slice(0, HINT_VALUES).join(", ")}`;
  }
  if (variable.rangeMin != null && variable.rangeMax != null) {
    return `${String(variable.rangeMin)} to ${String(variable.rangeMax)}`;
  }
  if (variable.dateMin != null && variable.dateMax != null) {
    return `${variable.dateMin.slice(0, 10)} to ${variable.dateMax.slice(0, 10)}`;
  }
  const subFilters = variable.subFilterVariableIds;
  return subFilters.length > 0 ? `${String(subFilters.length)} sub-filters` : "";
}

export function VariableRow({
  variable,
  current,
  isOpen,
  onOpenChange,
  onApply,
}: VariableRowProps) {
  const hint = variableHint(variable);
  const dataShape = variable.dataShape ?? "";
  return (
    <li>
      <Popover open={isOpen} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <button
            type="button"
            data-testid={`eda-variable-${variable.variableId}`}
            className="w-full rounded px-2 py-1 text-left hover:bg-accent"
          >
            <span className="flex items-center gap-1.5">
              <span className="truncate text-xs">{variable.displayName}</span>
              <Badge variant="outline" className="text-[10px]">
                {variable.variableType}
              </Badge>
              {dataShape !== "" ? (
                <Badge variant="outline" className="text-[10px]">
                  {dataShape}
                </Badge>
              ) : null}
              {variable.isMultiValued ? (
                <Badge variant="outline" className="text-[10px]">
                  multi-valued
                </Badge>
              ) : null}
            </span>
            {hint !== "" ? (
              <span className="block truncate text-[11px] text-muted-foreground">
                {hint}
              </span>
            ) : null}
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72">
          <FilterEditor
            variable={variable}
            current={current}
            onApply={onApply}
            onCancel={() => onOpenChange(false)}
          />
        </PopoverContent>
      </Popover>
    </li>
  );
}
