"use client";

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";
import type { ParamSpec, Search } from "@pathfinder/shared";
import { getParamSpecs } from "@/lib/api/sites";
import { normalizeRecordType } from "@/lib/utils/normalizeRecordType";
import { buildContextValues } from "@/lib/utils/buildContextValues";
import type { StepParameters } from "@/lib/types/stepParameters";
import { useParamSpecsQuery } from "@/lib/query/hooks/useParamSpecsQuery";

interface AdvancedOptions {
  siteId: string;
  recordType: string | null;
  searchName: string;
  selectedSearch: Search | null;
  isSearchNameAvailable: boolean;
  apiRecordTypeValue: string | null | undefined;
  resolveRecordTypeForSearch: (searchRecordType?: string | null) => string;
  contextValues?: StepParameters;
  enabled?: boolean;
}

type UseParamSpecsResult = {
  paramSpecs: ParamSpec[];
  isLoading: boolean;
  error: Error | null;
  /**
   * Whether a fetch ran to completion. A disabled query returns no data, no
   * error and no loading flag, which is an absent answer rather than an empty
   * one.
   */
  settled: boolean;
};

/**
 * Consolidated hook for fetching WDK parameter specifications.
 *
 * Simple usage (positional args):
 *   useParamSpecs(siteId, recordType, searchName)
 *
 * Advanced usage (options object — adds debounce, contextValues, record-type
 * resolution, and an enabled guard):
 *   useParamSpecs({ siteId, recordType, searchName, selectedSearch, ... })
 */
export function useParamSpecs(options: AdvancedOptions): UseParamSpecsResult;
export function useParamSpecs(
  siteId: string,
  recordType: string,
  searchName: string,
): UseParamSpecsResult;
export function useParamSpecs(
  siteIdOrOptions: string | AdvancedOptions,
  recordType?: string,
  searchName?: string,
): UseParamSpecsResult {
  const isAdvanced = typeof siteIdOrOptions === "object";

  const advancedResult = useParamSpecsAdvanced(
    isAdvanced
      ? siteIdOrOptions
      : {
          siteId: "",
          recordType: null,
          searchName: "",
          selectedSearch: null,
          isSearchNameAvailable: false,
          apiRecordTypeValue: null,
          resolveRecordTypeForSearch: () => "",
          enabled: false,
        },
  );

  const simpleResult = useParamSpecsSimple(
    isAdvanced ? "" : siteIdOrOptions,
    isAdvanced ? "" : recordType!,
    isAdvanced ? "" : searchName!,
  );

  return isAdvanced ? advancedResult : simpleResult;
}

// ---------------------------------------------------------------------------
// Simple variant — delegates to TanStack Query hook
// ---------------------------------------------------------------------------

function useParamSpecsSimple(
  siteId: string,
  recordType: string,
  searchName: string,
): UseParamSpecsResult {
  const { data, isLoading, error, isSuccess } = useParamSpecsQuery(
    siteId,
    recordType,
    searchName,
  );
  return {
    paramSpecs: data ?? [],
    isLoading,
    error: error ?? null,
    settled: isSuccess,
  };
}

// ---------------------------------------------------------------------------
// Advanced variant (debounce, contextValues, record-type resolution)
// ---------------------------------------------------------------------------

function useParamSpecsAdvanced({
  siteId,
  recordType,
  searchName,
  selectedSearch,
  isSearchNameAvailable: _isSearchNameAvailable,
  apiRecordTypeValue,
  resolveRecordTypeForSearch,
  contextValues,
  enabled = true,
}: AdvancedOptions): UseParamSpecsResult {
  const resolvedRecordType = (() => {
    const result = resolveRecordTypeForSearch(selectedSearch?.recordType);
    const preferred =
      (result !== "" ? result : null) ?? apiRecordTypeValue ?? recordType;
    return normalizeRecordType(preferred);
  })();

  const contextSerialized = JSON.stringify(buildContextValues(contextValues ?? {}));
  const [debouncedContext] = useDebounce(contextSerialized, 250);

  const queryEnabled =
    enabled &&
    searchName !== "" &&
    resolvedRecordType != null &&
    resolvedRecordType !== "";

  const { data, isLoading, error, isSuccess } = useQuery({
    queryKey: [
      "param-specs-advanced",
      siteId,
      resolvedRecordType,
      searchName,
      debouncedContext,
    ] as const,
    queryFn: () =>
      getParamSpecs(
        siteId,
        resolvedRecordType!,
        searchName,
        JSON.parse(debouncedContext) as Record<string, string>,
      ),
    enabled: queryEnabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    meta: { silent: true },
  });

  return {
    paramSpecs: data ?? [],
    isLoading,
    error: error ?? null,
    settled: isSuccess,
  };
}
