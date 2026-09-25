"use client";

import type { Step, ParamSpec } from "@pathfinder/shared";
import { Skeleton } from "@/components/ui/skeleton";
import { isHiddenParam, isAdvancedParam } from "./widgets/registry";
import { SearchPicker } from "./components/SearchPicker";
import { ParamFieldRenderer } from "./components/ParamFieldRenderer";
import {
  PhyleticProfileParam,
  claimsPhyleticParams,
} from "./widgets/PhyleticProfileParam";
import { AdvancedParamsGroup } from "./widgets/AdvancedParamsGroup";
import type { StepEditorState } from "./useStepEditorState";
import type { ParamFormValues } from "./hooks/useParamForm";

interface SearchTransformBodyProps {
  state: StepEditorState;
  step: Step;
  onSearchChange: (next: string | null) => void;
  onFieldChanged: (name: string, allValues: ParamFormValues) => void;
  onFieldBlurred: () => void;
}

export function SearchTransformBody({
  state,
  step,
  onSearchChange,
  onFieldChanged,
  onFieldBlurred,
}: SearchTransformBodyProps) {
  const { compositeSpecs, normalSpecs, advancedSpecs } = bucketSpecs(state.paramSpecs);

  const advancedHasErrors = advancedSpecs.some((s) => {
    const meta = state.form.getFieldMeta(s.name);
    return meta != null && meta.errors.length > 0;
  });

  const visibleCount = normalSpecs.length + advancedSpecs.length;
  const hasComposite = compositeSpecs.length > 0;
  const paramSpecsError = state.paramSpecsError;

  return (
    <div className="space-y-5">
      <SearchSection
        currentSearchName={step.searchName ?? null}
        currentSearchDisplay={
          state.selectedSearch?.displayName ?? step.searchName ?? "Pick a search"
        }
        searchOptions={state.searchOptions}
        recordTypes={state.recordTypeOptions}
        onChange={onSearchChange}
      />

      {state.stepValidationError != null && state.stepValidationError !== "" && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {state.stepValidationError}
        </div>
      )}

      {paramSpecsError != null ? (
        <div
          role="alert"
          data-testid="param-specs-error"
          className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          <p className="font-medium">Failed to load parameters for this search.</p>
          <p className="mt-1 text-xs">{paramSpecsError.message}</p>
        </div>
      ) : state.isLoading ? (
        <div data-testid="param-specs-loading" className="space-y-3">
          <Skeleton className="h-9 w-full rounded-md" />
          <Skeleton className="h-9 w-2/3 rounded-md" />
        </div>
      ) : visibleCount === 0 && !hasComposite ? (
        // Only a completed fetch can say a search has no parameters. A query
        // that never ran has no answer to report.
        state.paramSpecsSettled ? (
          <p className="text-xs text-muted-foreground">
            No parameter options available for this search.
          </p>
        ) : null
      ) : (
        <div className="space-y-4">
          {hasComposite && (
            <PhyleticProfileParam
              specs={compositeSpecs}
              allSpecs={state.paramSpecs}
              form={state.form}
            />
          )}

          {normalSpecs.map((spec) => (
            <ParamFieldRenderer
              key={spec.name}
              spec={spec}
              state={state}
              onFieldChanged={onFieldChanged}
              onFieldBlurred={onFieldBlurred}
            />
          ))}

          {advancedSpecs.length > 0 && (
            <AdvancedParamsGroup
              count={advancedSpecs.length}
              hasErrors={advancedHasErrors}
            >
              {advancedSpecs.map((spec) => (
                <ParamFieldRenderer
                  key={spec.name}
                  spec={spec}
                  state={state}
                  onFieldChanged={onFieldChanged}
                  onFieldBlurred={onFieldBlurred}
                />
              ))}
            </AdvancedParamsGroup>
          )}
        </div>
      )}
    </div>
  );
}

function SearchSection({
  currentSearchName,
  currentSearchDisplay,
  searchOptions,
  recordTypes,
  onChange,
}: {
  currentSearchName: string | null;
  currentSearchDisplay: string;
  searchOptions: StepEditorState["searchOptions"];
  recordTypes: StepEditorState["recordTypeOptions"];
  onChange: (next: string | null) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Search
      </p>
      <SearchPicker
        searches={searchOptions}
        recordTypes={recordTypes}
        value={currentSearchName}
        onChange={onChange}
        placeholder={currentSearchDisplay}
      />
    </div>
  );
}

interface BucketedSpecs {
  compositeSpecs: ParamSpec[];
  normalSpecs: ParamSpec[];
  advancedSpecs: ParamSpec[];
}

function bucketSpecs(specs: ParamSpec[]): BucketedSpecs {
  const claimedParamNames = new Set(claimsPhyleticParams(specs));
  const compositeSpecs: ParamSpec[] = [];
  const normalSpecs: ParamSpec[] = [];
  const advancedSpecs: ParamSpec[] = [];
  for (const spec of specs) {
    if (spec.name === "") continue;
    if (claimedParamNames.has(spec.name)) {
      compositeSpecs.push(spec);
      continue;
    }
    if (isHiddenParam(spec)) continue;
    if (isAdvancedParam(spec)) {
      advancedSpecs.push(spec);
    } else {
      normalSpecs.push(spec);
    }
  }
  return { compositeSpecs, normalSpecs, advancedSpecs };
}
