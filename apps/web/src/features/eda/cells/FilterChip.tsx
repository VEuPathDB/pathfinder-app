"use client";

import { XIcon } from "lucide-react";
import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";

import { filterSummary } from "@/lib/eda/filterSummary";

export interface FilterChipProps {
  filter: EdaFilter;
  displayName: string;
  onRemove: () => void;
}

export function FilterChip({ filter, displayName, onRemove }: FilterChipProps) {
  return (
    <span
      data-testid={`eda-filter-chip-${filter.entityId}-${filter.variableId}`}
      className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[11px]"
    >
      <span className="font-medium">{displayName}</span>
      <span className="text-muted-foreground">{filterSummary(filter)}</span>
      <button
        type="button"
        aria-label={`Remove filter on ${displayName}`}
        onClick={onRemove}
        className="rounded-full hover:bg-accent"
      >
        <XIcon className="size-3" />
      </button>
    </span>
  );
}
