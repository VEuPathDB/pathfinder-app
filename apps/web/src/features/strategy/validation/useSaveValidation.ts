import { useState } from "react";
import { useDebouncedCallback } from "use-debounce";
import type { Step } from "@strategist/shared";

export function useSaveValidation(args: {
  steps: Step[];
  buildStepSignature: (step: Step) => string;
  debounceMs?: number;
  validate: () => Promise<boolean>;
}) {
  const { steps, buildStepSignature, debounceMs = 500, validate } = args;

  const validationInputKey =
    steps.length === 0
      ? ""
      : steps
          .map((step) => `${step.id}:${buildStepSignature(step)}`)
          .sort()
          .join("|");

  const debouncedValidate = useDebouncedCallback(() => {
    void validate();
  }, debounceMs);

  const [prevKey, setPrevKey] = useState(validationInputKey);
  if (validationInputKey !== prevKey) {
    setPrevKey(validationInputKey);
    if (steps.length > 0) debouncedValidate();
  }
}
