"use client";

import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";
import type { GeneSearchResult } from "@pathfinder/shared";
import { searchGenes } from "@pathfinder/shared/generated/hooks/useSearchGenes";
import { getOrganismsQueryOptions } from "@pathfinder/shared/generated/hooks/useGetOrganisms";
import { useSessionStore } from "@/state/useSessionStore";

const PAGE_SIZE = 30;

interface GeneSearchState {
  query: string;
  setQuery: (q: string) => void;
  results: GeneSearchResult[];
  totalCount: number;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  setError: (err: string | null) => void;
  hasMore: boolean;
  loadMore: () => void;

  // Organism filter
  organisms: string[];
  selectedOrganism: string | null;
  setSelectedOrganism: (org: string | null) => void;
  organismFilter: string;
  setOrganismFilter: (f: string) => void;
  filteredOrganisms: string[];

  // Selection reset hook - called when search criteria change
  clearSelections: () => void;
}

export function useGeneSearch(onSelectionsCleared: () => void): GeneSearchState {
  const selectedSite = useSessionStore((s) => s.selectedSite);

  // Search state
  const [query, setQuery] = useState("");
  const [debouncedQuery] = useDebounce(query, 300);
  const [error, setError] = useState<string | null>(null);

  // Organism filter
  const { data: organismsResponse } = useQuery({
    ...getOrganismsQueryOptions(selectedSite),
    enabled: selectedSite !== "",
  });
  const organisms = organismsResponse?.organisms ?? [];
  const [selectedOrganism, setSelectedOrganism] = useState<string | null>(null);
  const [organismFilter, setOrganismFilter] = useState("");

  const filteredOrganisms = organisms.filter((org) =>
    org.toLowerCase().includes(organismFilter.toLowerCase()),
  );

  const clearKey = `${debouncedQuery}|${selectedOrganism}`;
  const [prevClearKey, setPrevClearKey] = useState(clearKey);
  if (clearKey !== prevClearKey) {
    setPrevClearKey(clearKey);
    onSelectionsCleared();
  }

  // Infinite query for gene search
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetching,
    isFetchingNextPage,
    error: queryError,
  } = useInfiniteQuery({
    queryKey: ["genes", "search", selectedSite, debouncedQuery, selectedOrganism],
    queryFn: ({ pageParam }) =>
      searchGenes(selectedSite, {
        q: debouncedQuery,
        organism: selectedOrganism,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (_lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.results.length, 0);
      const total = allPages[0]?.totalCount ?? 0;
      return loaded < total ? loaded : undefined;
    },
    enabled: debouncedQuery.trim().length > 0 && selectedSite !== "",
  });

  // Derive flat results from pages
  const results = data?.pages.flatMap((page) => page.results) ?? [];
  const totalCount = data?.pages[0]?.totalCount ?? 0;

  // Derive error string from query error or local error state
  const derivedError =
    error ?? (queryError instanceof Error ? queryError.message : null);

  return {
    query,
    setQuery,
    results,
    totalCount,
    loading: isFetching && !isFetchingNextPage,
    loadingMore: isFetchingNextPage,
    error: derivedError,
    setError,
    hasMore: hasNextPage,
    loadMore: () => {
      void fetchNextPage();
    },
    organisms,
    selectedOrganism,
    setSelectedOrganism,
    organismFilter,
    setOrganismFilter,
    filteredOrganisms,
    clearSelections: onSelectionsCleared,
  };
}
