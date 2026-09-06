import { useState, useRef } from "react";
import type { Experiment } from "@pathfinder/shared";
import {
  streamThresholdSweep,
  type ThresholdSweepPoint,
  type ThresholdSweepResult,
  type SweepRequest,
} from "@/features/workbench/analysis/api/compute";
import { useParamSpecs } from "@/lib/hooks/useParamSpecs";
import {
  isOptimizable,
  isNumericParam,
  isMultiPickParam,
  flattenVocab,
} from "../../utils/paramUtils";
import type { SweepableParam } from "./types";
import { fmtParamValue } from "../../utils/formatters";
import { MAX_CATEGORICAL_CHOICES } from "./types";

export function useSweepState(experiment: Experiment) {
  const { siteId, recordType, searchName } = experiment.config;
  const { paramSpecs, isLoading: specsLoading } = useParamSpecs(
    siteId,
    recordType,
    searchName,
  );

  const [paramName, setParamName] = useState("");
  const [minVal, setMinVal] = useState("");
  const [maxVal, setMaxVal] = useState("");
  const [steps, setSteps] = useState("10");
  const [selectedValues, setSelectedValues] = useState<Set<string>>(new Set());

  const [livePoints, setLivePoints] = useState<ThresholdSweepPoint[]>([]);
  const [completedCount, setCompletedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [finalResult, setFinalResult] = useState<ThresholdSweepResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sweepableParams = (() => {
    const configParams = experiment.config.parameters;
    if (paramSpecs.length === 0) return [];

    const result: SweepableParam[] = [];
    for (const spec of paramSpecs) {
      if (!isOptimizable(spec)) continue;
      if (isMultiPickParam(spec)) continue;
      if (!(spec.name in configParams)) continue;

      const currentValue = String(configParams[spec.name] ?? "");

      if (isNumericParam(spec)) {
        result.push({
          name: spec.name,
          displayName: spec.displayName ?? spec.name,
          kind: "numeric",
          currentValue,
          numericValue: Number(currentValue),
        });
      } else {
        const vocab = spec.vocabulary != null ? flattenVocab(spec.vocabulary) : [];
        if (vocab.length > 1) {
          result.push({
            name: spec.name,
            displayName: spec.displayName ?? spec.name,
            kind: "categorical",
            currentValue,
            vocab,
          });
        }
      }
    }
    return result;
  })();

  const selectedParam = sweepableParams.find((p) => p.name === paramName) ?? null;
  const sweepType = selectedParam?.kind ?? "numeric";

  const vocabDisplayMap = selectedParam?.vocab
    ? new Map(selectedParam.vocab.map((e) => [e.value, e.display]))
    : new Map<string, string>();

  const formatValue = (v: number | string): string => {
    if (sweepType === "categorical") {
      return vocabDisplayMap.get(String(v)) ?? String(v);
    }
    return typeof v === "number" ? fmtParamValue(v) : v;
  };

  const handleParamChange = (name: string) => {
    setParamName(name);
    setFinalResult(null);
    setLivePoints([]);
    setError(null);

    const param = sweepableParams.find((p) => p.name === name);
    if (!param) return;

    if (param.kind === "numeric" && param.numericValue != null) {
      const cv = param.numericValue;
      setMinVal(String(Math.max(0, cv * 0.2)));
      setMaxVal(String(cv * 3));
    }

    if (param.kind === "categorical" && param.vocab) {
      setSelectedValues(
        new Set(param.vocab.slice(0, MAX_CATEGORICAL_CHOICES).map((e) => e.value)),
      );
    }
  };

  const handleRun = async () => {
    if (!paramName || !selectedParam) return;
    setError(null);

    let request: SweepRequest;
    if (selectedParam.kind === "numeric") {
      const mn = parseFloat(minVal);
      const mx = parseFloat(maxVal);
      const st = parseInt(steps);
      if (isNaN(mn) || isNaN(mx) || isNaN(st)) return;
      if (mn >= mx) {
        setError("Minimum must be less than maximum");
        return;
      }
      request = {
        sweepType: "numeric",
        parameterName: paramName,
        min: mn,
        max: mx,
        steps: Math.max(3, Math.min(50, st)),
      };
    } else {
      const values = Array.from(selectedValues);
      if (values.length < 2) return;
      request = {
        sweepType: "categorical",
        parameterName: paramName,
        values,
      };
    }

    setLivePoints([]);
    setCompletedCount(0);
    setTotalCount(0);
    setFinalResult(null);
    setError(null);
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamThresholdSweep(
        experiment.id,
        request,
        {
          onPoint: (progress) => {
            setLivePoints((prev) => {
              const next = [...prev, progress.point];
              if (selectedParam.kind === "numeric") {
                next.sort((a, b) => Number(a.value) - Number(b.value));
              }
              return next;
            });
            setCompletedCount(progress.completedCount);
            setTotalCount(progress.totalCount);
          },
          onComplete: (result) => {
            setFinalResult(result);
          },
          onError: (err) => {
            setError(err.message);
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };

  const displayPoints = finalResult?.points ?? livePoints;
  const validPoints = displayPoints.filter((p) => p.metrics != null);
  const failedPoints = displayPoints.filter((p) => p.metrics == null);
  const activeSweepType = finalResult?.sweepType ?? sweepType;

  const canRun = Boolean(
    selectedParam &&
    (selectedParam.kind === "numeric"
      ? paramName && minVal && maxVal
      : selectedValues.size >= 2),
  );

  return {
    specsLoading,
    sweepableParams,
    selectedParam,
    sweepType,
    activeSweepType,
    formatValue,

    paramName,
    minVal,
    setMinVal,
    maxVal,
    setMaxVal,
    steps,
    setSteps,
    selectedValues,
    setSelectedValues,

    loading,
    error,
    completedCount,
    totalCount,
    finalResult,

    displayPoints,
    validPoints,
    failedPoints,
    canRun,

    handleParamChange,
    handleRun,
    handleCancel,
  };
}
