"use client";

import { useState } from "react";
import type { Step } from "@pathfinder/shared";
import { inferStepKind } from "@/features/strategy/graph";

interface UseStepMetadataArgs {
  step: Step;
}

export function useStepMetadata({ step }: UseStepMetadataArgs) {
  const [oldName, setOldName] = useState(step.displayName);
  const [name, setName] = useState(step.displayName);
  const [operatorValue, setOperatorValue] = useState(step.operator ?? "");
  const [colocationParams, setColocationParams] = useState(step.colocationParams);

  const kind = inferStepKind(step);
  const stepValidationError = step.validation?.errors?.general?.[0] ?? null;

  return {
    oldName,
    setOldName,
    name,
    setName,
    operatorValue,
    setOperatorValue,
    colocationParams,
    setColocationParams,
    kind,
    stepValidationError,
  };
}
