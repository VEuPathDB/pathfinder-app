"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2 } from "lucide-react";
import type { GeneSearchResult } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Gene detail hover popover
// ---------------------------------------------------------------------------

function GeneDetailPopover({
  gene,
  position,
  onMouseEnter,
  onMouseLeave,
}: {
  gene: GeneSearchResult;
  position: { top: number; right: number };
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  return createPortal(
    <div
      className="pointer-events-auto fixed z-50 w-64 rounded-lg border border-border bg-popover p-3 shadow-lg"
      style={{ top: position.top, right: position.right }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <p className="text-xs font-semibold text-foreground">
        {gene.displayName !== "" && gene.displayName != null
          ? gene.displayName
          : gene.geneId}
      </p>
      <p className="text-[10px] text-muted-foreground">{gene.geneId}</p>
      <dl className="mt-2 space-y-1 text-[10px]">
        <div>
          <dt className="font-medium text-muted-foreground">Product</dt>
          <dd className="text-foreground">
            {gene.product !== "" && gene.product != null ? gene.product : "-"}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Organism</dt>
          <dd className="italic text-foreground">{gene.organism}</dd>
        </div>
        {gene.geneName !== "" && gene.geneName != null && (
          <div>
            <dt className="font-medium text-muted-foreground">Gene name</dt>
            <dd className="text-foreground">{gene.geneName}</dd>
          </div>
        )}
        {gene.geneType !== "" && gene.geneType != null && (
          <div>
            <dt className="font-medium text-muted-foreground">Type</dt>
            <dd className="text-foreground">{gene.geneType}</dd>
          </div>
        )}
        {gene.location !== "" && gene.location != null && (
          <div>
            <dt className="font-medium text-muted-foreground">Location</dt>
            <dd className="text-foreground">{gene.location}</dd>
          </div>
        )}
      </dl>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Gene row
// ---------------------------------------------------------------------------

function GeneRow({
  gene,
  selected,
  onToggle,
  onMouseEnter,
  onMouseLeave,
}: {
  gene: GeneSearchResult;
  selected: boolean;
  onToggle: () => void;
  onMouseEnter: (e: React.MouseEvent<HTMLDivElement>) => void;
  onMouseLeave: () => void;
}) {
  return (
    <div
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="flex items-start gap-2 border-b border-border/50 px-3 py-1.5 transition-colors hover:bg-accent/50"
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-border"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-foreground">
          {gene.displayName !== "" && gene.displayName != null
            ? gene.displayName
            : gene.product !== "" && gene.product != null
              ? gene.product
              : gene.geneId}
        </p>
        <p className="truncate text-[10px] text-muted-foreground">{gene.geneId}</p>
        <p className="truncate text-[10px] italic text-muted-foreground">
          {gene.organism}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main results component
// ---------------------------------------------------------------------------

interface GeneSearchResultsProps {
  results: GeneSearchResult[];
  totalCount: number;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  query: string;
  hasMore: boolean;
  onLoadMore: () => void;
  selectedIds: Set<string>;
  onToggleSelect: (geneId: string) => void;
  onToggleSelectAll: () => void;
  sidebarRef: React.RefObject<HTMLElement | null>;
}

export function GeneSearchResults({
  results,
  totalCount,
  loading,
  loadingMore,
  error,
  query,
  hasMore,
  onLoadMore,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  sidebarRef,
}: GeneSearchResultsProps) {
  // Hover detail state
  const [hoveredGene, setHoveredGene] = useState<GeneSearchResult | null>(null);
  const [hoverPos, setHoverPos] = useState({ top: 0, right: 0 });
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = (
    gene: GeneSearchResult,
    e: React.MouseEvent<HTMLDivElement>,
  ) => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    const rect = e.currentTarget.getBoundingClientRect();
    const sidebarRect = sidebarRef.current?.getBoundingClientRect();
    hoverTimeoutRef.current = setTimeout(() => {
      setHoveredGene(gene);
      setHoverPos({
        top: rect.top,
        right: window.innerWidth - (sidebarRect?.left ?? rect.left) + 8,
      });
    }, 300);
  };

  const handleMouseLeave = () => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    setHoveredGene(null);
  };

  const handlePopoverEnter = () => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error != null && error !== "") {
    return (
      <div className="px-3 py-6 text-center text-xs text-destructive">{error}</div>
    );
  }

  if (results.length === 0 && query.trim()) {
    return (
      <div className="px-3 py-8 text-center text-xs text-muted-foreground">
        No genes found.
      </div>
    );
  }

  if (results.length === 0) return null;

  return (
    <>
      {/* Select all */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
        <input
          type="checkbox"
          checked={results.length > 0 && selectedIds.size === results.length}
          onChange={onToggleSelectAll}
          className="h-3.5 w-3.5 rounded border-border"
        />
        <span className="text-[10px] text-muted-foreground">Select all</span>
      </div>

      {results.map((gene) => (
        <GeneRow
          key={gene.geneId}
          gene={gene}
          selected={selectedIds.has(gene.geneId)}
          onToggle={() => onToggleSelect(gene.geneId)}
          onMouseEnter={(e) => handleMouseEnter(gene, e)}
          onMouseLeave={handleMouseLeave}
        />
      ))}

      {/* Load more */}
      {hasMore && (
        <div className="px-3 py-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              `Load more (${results.length} of ${totalCount})`
            )}
          </Button>
        </div>
      )}

      {/* Hover popover */}
      {hoveredGene && (
        <GeneDetailPopover
          gene={hoveredGene}
          position={hoverPos}
          onMouseEnter={handlePopoverEnter}
          onMouseLeave={handleMouseLeave}
        />
      )}
    </>
  );
}
