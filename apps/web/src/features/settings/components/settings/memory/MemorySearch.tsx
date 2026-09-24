"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";
import { Search } from "lucide-react";

import type { MemoryItem } from "@pathfinder/shared";

import { searchMemories } from "@/features/settings/api/memories";
import { Input } from "@/components/ui/input";

import { MemoryRow } from "./MemoryRow";

interface MemorySearchProps {
  onEdit?: (item: MemoryItem) => void;
  onDelete?: (item: MemoryItem) => void;
  onToggleAutoRetrieve?: (item: MemoryItem, next: boolean) => void;
}

const DEBOUNCE_MS = 300;

const noop = () => {};
const noopToggle = () => {};

export function MemorySearch({
  onEdit,
  onDelete,
  onToggleAutoRetrieve,
}: MemorySearchProps = {}) {
  const [query, setQuery] = useState("");
  const [debouncedQuery] = useDebounce(query, DEBOUNCE_MS);
  const trimmed = debouncedQuery.trim();

  const { data, isFetching, error } = useQuery({
    queryKey: ["memories", "search", trimmed],
    queryFn: () => searchMemories(trimmed),
    enabled: trimmed.length > 0,
    staleTime: 10_000,
    meta: { shownInline: true },
  });

  const hits = data?.hits ?? [];
  const showResults = trimmed.length > 0 && !isFetching;

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search memories..."
          className="pl-8"
          aria-label="Search memories"
        />
      </div>
      {trimmed.length > 0 && (
        <div className="rounded-md border border-border">
          {isFetching && (
            <div className="px-3 py-2 text-xs text-muted-foreground">Searching...</div>
          )}
          {error != null && (
            <div className="px-3 py-2 text-xs text-destructive">
              Search failed: {error instanceof Error ? error.message : "unknown"}
            </div>
          )}
          {showResults && hits.length === 0 && error == null && (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              No memories matched &ldquo;{trimmed}&rdquo;.
            </div>
          )}
          {showResults && hits.length > 0 && (
            <div>
              {hits.map((hit, idx) => (
                <MemoryRow
                  key={hit.key === "" ? `${hit.value.name}-${idx}` : hit.key}
                  item={hit}
                  onEdit={onEdit ?? noop}
                  onDelete={onDelete ?? noop}
                  onToggleAutoRetrieve={onToggleAutoRetrieve ?? noopToggle}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
