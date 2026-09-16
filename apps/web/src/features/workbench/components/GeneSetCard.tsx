"use client";

import type { GeneSet } from "@pathfinder/shared";
import { cn } from "@/lib/utils/cn";
import { SOURCE_CONFIG } from "./geneSetSourceConfig";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const OP_SYMBOLS: Record<string, string> = {
  intersect: "\u2229",
  union: "\u222A",
  minus: "\u2212",
};

interface GeneSetCardProps {
  geneSet: GeneSet;
  isActive: boolean;
  isSelected: boolean;
  /** Gene IDs of the currently active set, used to compute overlap. */
  activeGeneIds: string[];
  onActivate: () => void;
  onToggleSelect: () => void;
}

export function GeneSetCard({
  geneSet,
  isActive,
  isSelected,
  activeGeneIds,
  onActivate,
  onToggleSelect,
}: GeneSetCardProps) {
  const { icon: Icon } = SOURCE_CONFIG[geneSet.source];

  // Compute overlap percentage with the active set
  const overlapPct = (() => {
    const ids = geneSet.geneIds;
    if (activeGeneIds.length === 0 || ids.length === 0) return null;
    if (isActive) return 100;
    const activeSet = new Set(activeGeneIds);
    const overlap = ids.filter((id) => activeSet.has(id)).length;
    return Math.round((overlap / ids.length) * 100);
  })();

  // Provenance for derived sets
  const provenance = (() => {
    if (geneSet.source !== "derived" || !geneSet.operation) return null;
    const symbol = OP_SYMBOLS[geneSet.operation] ?? geneSet.operation;
    return `${symbol} derived`;
  })();

  return (
    <div
      className={cn(
        "group relative flex items-start gap-2 rounded-lg px-3 py-2 transition-all duration-150",
        isActive ? "bg-muted" : "hover:bg-muted/40",
        isSelected && !isActive && "bg-muted/30",
      )}
    >
      {/* Selection checkbox */}
      <label className="mt-1 flex shrink-0 items-center">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => {
            e.stopPropagation();
            onToggleSelect();
          }}
          className="h-3.5 w-3.5 cursor-pointer rounded border-border accent-primary"
          aria-label={`Select ${geneSet.name}`}
        />
      </label>

      {/* Clickable body */}
      <button
        type="button"
        onClick={onActivate}
        className="min-w-0 flex-1 overflow-hidden text-left"
      >
        {/* Row 1: icon + name + count */}
        <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
          <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span
            className="min-w-0 flex-1 truncate text-sm font-medium text-foreground"
            title={geneSet.name}
          >
            {geneSet.name}
          </span>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {geneSet.geneCount.toLocaleString()}
          </span>
        </div>

        {/* Row 2: overlap bar */}
        {overlapPct !== null && (
          <div className="mt-1.5 flex items-center gap-2">
            <div
              className={cn(
                "h-1 flex-1 overflow-hidden rounded-full bg-border",
                // De-emphasize only the decorative bar on the active row -
                // fading the % text too would drop it below contrast.
                isActive && "opacity-40",
              )}
            >
              <div
                className="h-full rounded-full bg-primary/50 transition-all duration-300"
                style={{ width: `${overlapPct}%` }}
              />
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
                  {overlapPct}%
                </span>
              </TooltipTrigger>
              <TooltipContent side="right">
                {isActive ? "Active set" : "Overlap with active set"}
              </TooltipContent>
            </Tooltip>
          </div>
        )}

        {/* Row 3: provenance for derived sets */}
        {provenance != null && provenance !== "" && (
          <p className="mt-0.5 text-[10px] text-muted-foreground">{provenance}</p>
        )}
      </button>
    </div>
  );
}
