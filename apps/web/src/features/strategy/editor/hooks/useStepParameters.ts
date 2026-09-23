"use client";

import type { ParamSpec, Search, StepKind } from "@pathfinder/shared";
import type { StepParameters } from "@/lib/types/stepParameters";
import { useParamSpecs } from "@/lib/hooks/useParamSpecs";
import { isInputStepParam } from "@/features/strategy/parameters/spec";
import type { ParamFormValues } from "./useParamForm";
import { extractVocabOptions, type VocabOption } from "@/lib/utils/vocab";
import { extractSpecVocabulary } from "../components/stepEditorUtils";

interface UseStepParametersArgs {
  siteId: string;
  recordType: string | null;
  kind: StepKind;
  searchName: string;
  selectedSearch: Search | null;
  isSearchNameAvailable: boolean;
  apiRecordTypeValue: string | null | undefined;
  resolveRecordTypeForSearch: (searchRecordType?: string | null) => string;
  stepParameters: StepParameters | undefined;
}

/**
 * Read-only param state - fetches `paramSpecs` and computes vocab + hidden
 * defaults. Form values are owned by `useParamForm`; dependent-param refresh
 * is owned by `useDependentParamRefresh`.
 *
 * `stepParameters` is the persisted `step.parameters` map: passed to
 * `/param-specs` as `contextValues` so WDK echoes the user's saved values
 * back through `initialDisplayValue` (instead of WDK's own defaults).
 */
export function useStepParameters({
  siteId,
  recordType,
  kind,
  searchName,
  selectedSearch,
  isSearchNameAvailable,
  apiRecordTypeValue,
  resolveRecordTypeForSearch,
  stepParameters,
}: UseStepParametersArgs) {
  const { paramSpecs, isLoading, error, settled } = useParamSpecs({
    siteId,
    recordType,
    searchName,
    selectedSearch,
    isSearchNameAvailable,
    apiRecordTypeValue,
    resolveRecordTypeForSearch,
    ...(stepParameters !== undefined ? { contextValues: stepParameters } : {}),
    enabled: kind !== "combine",
  });

  const vocabOptions = paramSpecs.reduce<Record<string, VocabOption[]>>((acc, spec) => {
    if (spec.name === "") return acc;
    const vocabulary = extractSpecVocabulary(spec);
    if (vocabulary != null) {
      acc[spec.name] = extractVocabOptions(vocabulary);
    }
    return acc;
  }, {});

  return {
    paramSpecs,
    settled,
    isLoading,
    error,
    vocabOptions,
    hiddenDefaults: hiddenParamDefaults(paramSpecs),
  };
}

export function hiddenParamDefaults(paramSpecs: ParamSpec[]): ParamFormValues {
  const hiddenDefaults: ParamFormValues = {};
  for (const spec of paramSpecs) {
    if (spec.isVisible !== false || spec.name === "" || isInputStepParam(spec))
      continue;
    if (spec.initialDisplayValue != null) {
      hiddenDefaults[spec.name] = spec.initialDisplayValue;
    }
  }
  return hiddenDefaults;
}
