"use client";

import { useRef } from "react";
import { ChevronRight, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useGeneSearch } from "../hooks/useGeneSearch";
import { useGeneSelection } from "../hooks/useGeneSelection";
import { OrganismFilter } from "./OrganismFilter";
import { GeneSearchResults } from "./GeneSearchResults";
import { GeneSearchActions } from "./GeneSearchActions";

interface GeneSearchSidebarProps {
  onCollapse?: () => void;
}

export function GeneSearchSidebar({ onCollapse }: GeneSearchSidebarProps) {
  const sidebarRef = useRef<HTMLElement>(null);

  const selection = useGeneSelection();

  const search = useGeneSearch(selection.clearSelection);

  return (
    <aside ref={sidebarRef} className="relative flex h-full flex-col overflow-hidden">
      {/* Header + Search input + organism filter + result count */}
      <div className="space-y-2 border-b border-border px-3 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Gene Search
          </h3>
          {onCollapse && (
            <button
              type="button"
              onClick={onCollapse}
              aria-label="Collapse gene search"
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            value={search.query}
            onChange={(e) => search.setQuery(e.target.value)}
            placeholder="Search genes..."
            className="h-8 bg-background pl-8 pr-3 text-xs"
          />
        </div>

        <OrganismFilter
          organisms={search.organisms}
          selectedOrganism={search.selectedOrganism}
          onSelect={search.setSelectedOrganism}
          organismFilter={search.organismFilter}
          onFilterChange={search.setOrganismFilter}
          filteredOrganisms={search.filteredOrganisms}
        />

        {/* Result count */}
        {search.query.trim() && !search.loading && (
          <p className="text-[10px] text-muted-foreground">
            {search.totalCount.toLocaleString()} result
            {search.totalCount !== 1 ? "s" : ""}
            {selection.hasSelection && (
              <span className="ml-1 font-medium text-primary">
                ({selection.selectedIds.size} selected)
              </span>
            )}
          </p>
        )}
      </div>

      {/* Results list */}
      <div className="flex-1 overflow-y-auto">
        <GeneSearchResults
          results={search.results}
          totalCount={search.totalCount}
          loading={search.loading}
          loadingMore={search.loadingMore}
          error={search.error}
          query={search.query}
          hasMore={search.hasMore}
          onLoadMore={search.loadMore}
          selectedIds={selection.selectedIds}
          onToggleSelect={selection.toggleSelect}
          onToggleSelectAll={() => selection.toggleSelectAll(search.results)}
          sidebarRef={sidebarRef}
        />
      </div>

      {/* Action bar */}
      <GeneSearchActions
        selectedIds={selection.selectedIds}
        query={search.query}
        onClearSelection={selection.clearSelection}
        onError={search.setError}
      />
    </aside>
  );
}
