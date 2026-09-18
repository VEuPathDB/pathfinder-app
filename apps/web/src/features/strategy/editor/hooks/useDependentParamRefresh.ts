"use client";

import { useRef, useState, startTransition } from "react";
import { toast } from "sonner";
import type { ParamSpec } from "@pathfinder/shared";
import { refreshDependentParams } from "@/lib/api/sites";
import { extractVocabOptions, type VocabOption } from "@/lib/utils/vocab";
import { extractSpecVocabulary } from "@/features/strategy/editor/components/stepEditorUtils";
import { rawToParamValue } from "@/features/strategy/parameters/paramValue";
import { statesNothing } from "@/lib/parameters/paramValue";
import type { StepParameters } from "@/lib/types/stepParameters";
import type { ParamFormValues } from "./useParamForm";

interface UseDependentParamRefreshArgs {
  siteId: string;
  recordType: string;
  searchName: string;
  specs: ParamSpec[];
  /** Called when an existing dependent value becomes invalid after refresh. */
  onClearStaleValue?: (paramName: string) => void;
}

interface DependentRefreshState {
  dependentOptions: Record<string, VocabOption[]>;
  dependentLoading: Record<string, boolean>;
  dependentErrors: Record<string, string | null>;
  /**
   * Call this with the changed parameter name and the latest form values. The
   * refresh runs only if that parameter declares `dependentParams`.
   */
  handleFieldChange: (changedName: string, allValues: ParamFormValues) => void;
}

export function useDependentParamRefresh(
  args: UseDependentParamRefreshArgs,
): DependentRefreshState {
  const { siteId, recordType, searchName, specs, onClearStaleValue } = args;
  const [dependentOptions, setDependentOptions] = useState<
    Record<string, VocabOption[]>
  >({});
  const [dependentLoading, setDependentLoading] = useState<Record<string, boolean>>({});
  const [dependentErrors, setDependentErrors] = useState<Record<string, string | null>>(
    {},
  );
  const refreshCounterRef = useRef(0);

  const handleFieldChange = (changedName: string, allValues: ParamFormValues) => {
    const changedSpec = specs.find((s) => s.name === changedName);
    const depParams = changedSpec?.dependentParams;
    if (depParams == null || depParams.length === 0) return;

    const counter = ++refreshCounterRef.current;
    setDependentLoading((prev) => {
      const next = { ...prev };
      for (const dep of depParams) next[dep] = true;
      return next;
    });
    setDependentErrors((prev) => {
      const next = { ...prev };
      for (const dep of depParams) next[dep] = null;
      return next;
    });

    // WDK reads the context as typed values. A value that states nothing is
    // left out, because the wire refuses an empty one.
    const contextValues: StepParameters = {};
    for (const spec of specs) {
      const raw = allValues[spec.name];
      if (raw === undefined) continue;
      const value = rawToParamValue(spec, raw);
      if (statesNothing(value)) continue;
      contextValues[spec.name] = value;
    }

    refreshDependentParams(siteId, recordType, searchName, changedName, contextValues)
      .then((refreshedSpecs) => {
        if (refreshCounterRef.current !== counter) return;
        startTransition(() => {
          setDependentOptions((prev) => {
            const next = { ...prev };
            for (const spec of refreshedSpecs) {
              if (!spec.name) continue;
              const vocab = extractSpecVocabulary(spec);
              if (vocab != null) {
                next[spec.name] = extractVocabOptions(vocab);
              }
            }
            return next;
          });
          setDependentLoading((prev) => {
            const next = { ...prev };
            for (const dep of depParams) next[dep] = false;
            return next;
          });
        });

        if (onClearStaleValue == null) return;
        for (const refreshed of refreshedSpecs) {
          if (!refreshed.name || !depParams.includes(refreshed.name)) continue;
          const currentValue = allValues[refreshed.name];
          if (currentValue === undefined || currentValue === "") continue;
          const vocab = extractSpecVocabulary(refreshed);
          const newOptions = vocab != null ? extractVocabOptions(vocab) : [];
          const validValues = new Set(newOptions.map((o) => o.value));
          const isValid = Array.isArray(currentValue)
            ? currentValue.every((v) => validValues.has(v))
            : validValues.has(currentValue);
          if (!isValid) {
            onClearStaleValue(refreshed.name);
            toast.warning(
              `Updated options for ${refreshed.displayName ?? refreshed.name}. Please re-select.`,
            );
          }
        }
      })
      .catch((err: unknown) => {
        if (refreshCounterRef.current !== counter) return;
        const msg = err instanceof Error ? err.message : String(err);
        setDependentErrors((prev) => {
          const next = { ...prev };
          for (const dep of depParams) next[dep] = msg;
          return next;
        });
        setDependentLoading((prev) => {
          const next = { ...prev };
          for (const dep of depParams) next[dep] = false;
          return next;
        });
      });
  };

  return {
    dependentOptions,
    dependentLoading,
    dependentErrors,
    handleFieldChange,
  };
}
