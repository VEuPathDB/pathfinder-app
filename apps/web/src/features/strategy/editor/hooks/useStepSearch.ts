"use client";

import { useState } from "react";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { Search } from "@strategist/shared";
import { searchesOptions } from "@/lib/api/sites";
import { normalizeRecordType } from "@/lib/utils/normalizeRecordType";

interface UseStepSearchArgs {
  siteId: string;
  /** The strategy-level record type. */
  recordType: string | null;
  /** Initial search name from the step. */
  initialSearchName: string;
  /** Resolves record type for search fetching. */
  resolveRecordTypeForSearch: (searchRecordType?: string | null) => string;
}

export function useStepSearch({
  siteId,
  recordType,
  initialSearchName,
  resolveRecordTypeForSearch,
}: UseStepSearchArgs) {
  const [editableSearchName, setEditableSearchName] = useState(initialSearchName);

  const searchName = editableSearchName.trim();

  const resolvedRecordType = resolveRecordTypeForSearch();
  const normalizedRecordType = normalizeRecordType(resolvedRecordType || recordType);

  const { enabled: _enabled, ...searchOpts } = searchesOptions(
    siteId,
    normalizedRecordType,
  );
  const { data: rawSearches } = useSuspenseQuery(searchOpts);

  const searchOptions: Search[] = [...rawSearches].sort((a, b) =>
    (a.displayName || a.name).localeCompare(b.displayName || b.name),
  );

  const selectedSearch =
    searchName === ""
      ? null
      : (searchOptions.find((option) => option.name === searchName) ?? null);

  const isSearchNameAvailable =
    searchName !== ""
      ? searchOptions.some((option) => option.name === searchName)
      : true;

  const filteredSearchOptions = (() => {
    const query = editableSearchName.trim().toLowerCase();
    if (query === "") return searchOptions;
    return searchOptions.filter((option) => {
      const label = (option.displayName || option.name).toLowerCase();
      return label.includes(query) || option.name.toLowerCase().includes(query);
    });
  })();

  return {
    editableSearchName,
    setEditableSearchName,
    searchName,
    selectedSearch,
    isSearchNameAvailable,
    searchOptions,
    filteredSearchOptions,
  };
}
