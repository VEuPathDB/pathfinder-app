"use client";

import type { Step } from "@strategist/shared";
import { useStepMetadata } from "./hooks/useStepMetadata";
import { useStepRecordType } from "./hooks/useStepRecordType";
import { useStepSearch } from "./hooks/useStepSearch";
import { useStepParameters } from "./hooks/useStepParameters";
import { useParamForm } from "./hooks/useParamForm";
import { useDependentParamRefresh } from "./hooks/useDependentParamRefresh";

interface UseStepEditorStateArgs {
  step: Step;
  siteId: string;
  recordType: string | null;
}

/**
 * Composed editor state. Form values are SSOT for in-flight edits; saving
 * is owned by the caller via mutations (useUpdateStepMutation).
 */
export function useStepEditorState({
  step,
  siteId,
  recordType,
}: UseStepEditorStateArgs) {
  const metadata = useStepMetadata({ step });

  const recordTypeState = useStepRecordType({
    siteId,
    recordType,
    initialRecordType: step.recordType ?? recordType,
  });

  const searchState = useStepSearch({
    siteId,
    recordType,
    initialSearchName: step.searchName ?? "",
    resolveRecordTypeForSearch: recordTypeState.resolveRecordTypeForSearch,
  });

  const stepParameters = step.parameters ?? undefined;

  const paramState = useStepParameters({
    siteId,
    recordType,
    kind: metadata.kind,
    searchName: searchState.searchName,
    selectedSearch: searchState.selectedSearch,
    isSearchNameAvailable: searchState.isSearchNameAvailable,
    apiRecordTypeValue: recordTypeState.apiRecordTypeValue,
    resolveRecordTypeForSearch: recordTypeState.resolveRecordTypeForSearch,
    stepParameters,
  });

  const { form, hydrated: paramFormHydrated } = useParamForm(
    paramState.paramSpecs,
    stepParameters,
  );

  const dependent = useDependentParamRefresh({
    siteId,
    recordType: recordTypeState.apiRecordTypeValue ?? recordType ?? "",
    searchName: searchState.searchName,
    specs: paramState.paramSpecs,
    onClearStaleValue: (paramName) => {
      form.setFieldValue(paramName, "");
    },
  });

  return {
    kind: metadata.kind,
    stepValidationError: metadata.stepValidationError,

    oldName: metadata.oldName,
    name: metadata.name,
    setName: metadata.setName,

    siteId,
    editableSearchName: searchState.editableSearchName,
    setEditableSearchName: searchState.setEditableSearchName,
    searchName: searchState.searchName,
    selectedSearch: searchState.selectedSearch,
    isSearchNameAvailable: searchState.isSearchNameAvailable,
    searchOptions: searchState.searchOptions,
    filteredSearchOptions: searchState.filteredSearchOptions,

    recordTypeValue: recordTypeState.recordTypeValue,
    setRecordTypeValue: recordTypeState.setRecordTypeValue,
    normalizedRecordTypeValue: recordTypeState.normalizedRecordTypeValue,
    recordTypeFilter: recordTypeState.recordTypeFilter,
    setRecordTypeFilter: recordTypeState.setRecordTypeFilter,
    recordTypeOptions: recordTypeState.recordTypeOptions,
    filteredRecordTypes: recordTypeState.filteredRecordTypes,
    recordType,

    paramSpecs: paramState.paramSpecs,
    vocabOptions: paramState.vocabOptions,
    hiddenDefaults: paramState.hiddenDefaults,
    dependentOptions: dependent.dependentOptions,
    dependentLoading: dependent.dependentLoading,
    dependentErrors: dependent.dependentErrors,
    onDependentFieldChange: dependent.handleFieldChange,
    isLoading: paramState.isLoading,
    paramSpecsError: paramState.error,
    paramSpecsSettled: paramState.settled,

    operatorValue: metadata.operatorValue,
    setOperatorValue: metadata.setOperatorValue,
    colocationParams: metadata.colocationParams,
    setColocationParams: metadata.setColocationParams,

    form,
    paramFormHydrated,
  };
}

export type StepEditorState = ReturnType<typeof useStepEditorState>;
