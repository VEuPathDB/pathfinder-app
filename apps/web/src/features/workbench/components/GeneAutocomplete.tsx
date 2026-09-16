"use client";

import { useRef, useState } from "react";
import { useOnClickOutside } from "usehooks-ts";
import { useDebounce } from "use-debounce";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import type { GeneSearchResult } from "@pathfinder/shared";
import { searchGenes } from "@pathfinder/shared/generated/hooks/useSearchGenes";
import { Input } from "@/components/ui/input";

interface GeneAutocompleteProps {
  siteId: string;
  onSelect: (geneId: string) => void;
  placeholder?: string;
  excludeIds?: Set<string>;
}

export function GeneAutocomplete({
  siteId,
  onSelect,
  placeholder = "Search genes...",
  excludeIds,
}: GeneAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [debouncedQuery] = useDebounce(query, 300);
  const trimmedQuery = debouncedQuery.trim();

  const { data: searchResults, isFetching } = useQuery({
    queryKey: ["genes", "search", siteId, trimmedQuery] as const,
    queryFn: () => searchGenes(siteId, { q: trimmedQuery, limit: 10 }),
    enabled: trimmedQuery.length > 0 && siteId !== "",
    staleTime: 30_000,
  });

  const results =
    searchResults == null
      ? []
      : excludeIds
        ? searchResults.results.filter((r) => !excludeIds.has(r.geneId))
        : searchResults.results;

  const hasResults = trimmedQuery.length > 0 && results.length > 0;
  const open = hasResults && !dismissed;

  const [prevTrimmedQuery, setPrevTrimmedQuery] = useState(trimmedQuery);
  if (trimmedQuery !== prevTrimmedQuery) {
    setPrevTrimmedQuery(trimmedQuery);
    if (dismissed) setDismissed(false);
  }

  // Close on outside click
  useOnClickOutside(dropdownRef as React.RefObject<HTMLElement>, () =>
    setDismissed(true),
  );

  const handleSelect = (geneId: string) => {
    onSelect(geneId);
    setQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setDismissed(true);
    }
  };

  return (
    <div ref={dropdownRef} className="relative">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="h-7 bg-background pl-7 pr-7 text-xs"
        />
        {isFetching && (
          <Loader2 className="absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-48 overflow-y-auto rounded-md border border-border bg-popover shadow-lg animate-hover-card-in">
          {results.map((gene: GeneSearchResult) => (
            <button
              key={gene.geneId}
              type="button"
              data-testid="gene-autocomplete-result"
              data-gene-id={gene.geneId}
              onClick={() => handleSelect(gene.geneId)}
              className="flex w-full items-start gap-2 px-3 py-2 text-left transition-colors duration-75 hover:bg-accent"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-xs font-medium text-foreground">
                  {gene.geneId}
                </p>
                <p className="truncate text-[10px] text-muted-foreground">
                  {gene.product != null && gene.product !== "" ? gene.product : "-"}
                </p>
                <p className="truncate text-[10px] italic text-muted-foreground">
                  {gene.organism}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
