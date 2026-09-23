import { useShallow } from "zustand/react/shallow";
import type { ValidationErrors, Step } from "@pathfinder/shared";
import { useStrategyStore } from "./store";
import {
  STEP_LIFECYCLE_STATE_NAMES,
  type StepLifecycleStateName,
  type StepMachineSnapshot,
} from "./stepMachine";

export interface StepSnapshot {
  step: Step | null;
  /** Current XState v5 leaf state for the step. */
  lifecycleState: StepLifecycleStateName;
  /** The count on the wire; the lifecycle cache fills in when it carries none. */
  estimatedSize: number | null;
  /** Validation errors from the lifecycle machine, falling back to wire. */
  validationErrors: ValidationErrors | null;
  /** Last transient error (network/server) from the lifecycle machine. */
  lastError: string | null;
  /** True when the lifecycle is in validating or running. */
  isBusy: boolean;
  /** True when the step has a hard validation failure. */
  isInvalid: boolean;
  /** True when the step suffered a transient run/validation failure. */
  isFailed: boolean;
  /**
   * True when the step is deliberately unfinished - missing a required
   * parameter, or a combine that is not fully wired. The backend derives it.
   */
  isDraft: boolean;
  /**
   * Why WDK rejected this step's last push, if it did. The server keeps the
   * edit, and the rejection travels with the step.
   */
  wdkPushError: string | null;
}

function pickLifecycleValue(
  snapshot: StepMachineSnapshot | undefined,
): StepLifecycleStateName {
  const value = snapshot?.value;
  return STEP_LIFECYCLE_STATE_NAMES.find((name) => name === value) ?? "idle";
}

/**
 * The count the server sent, or the canvas's own for a step it does not count.
 * VEuPathDB owns a step's size, so the wire outranks the lifecycle cache.
 */
function resolveEstimatedSize(
  snapshot: StepMachineSnapshot | undefined,
  wire: Step | null,
): number | null {
  const wireSize = wire?.estimatedSize;
  if (typeof wireSize === "number") return wireSize;
  return snapshot?.context.estimatedSize ?? null;
}

const wireErrorsCache = new WeakMap<object, ValidationErrors>();

function resolveValidationErrors(
  snapshot: StepMachineSnapshot | undefined,
  wire: Step | null,
): ValidationErrors | null {
  if (snapshot?.context.validationErrors) {
    return snapshot.context.validationErrors;
  }
  const wireErrors = wire?.validation?.errors;
  if (!wireErrors) return null;
  const cached = wireErrorsCache.get(wireErrors);
  if (cached) return cached;
  const normalized: ValidationErrors = {
    general: wireErrors.general ?? [],
    byKey: wireErrors.byKey ?? {},
  };
  wireErrorsCache.set(wireErrors, normalized);
  return normalized;
}

export function useStepSnapshot(step: Step | null): StepSnapshot {
  return useStrategyStore(
    useShallow((state) => {
      const lifecycle = step !== null ? state.stepLifecycleById[step.id] : undefined;
      const lifecycleState = pickLifecycleValue(lifecycle);
      return {
        step,
        lifecycleState,
        estimatedSize: resolveEstimatedSize(lifecycle, step),
        validationErrors: resolveValidationErrors(lifecycle, step),
        lastError: lifecycle?.context.lastError ?? null,
        isBusy: lifecycleState === "validating" || lifecycleState === "running",
        isInvalid: lifecycleState === "invalid",
        isFailed: lifecycleState === "failed",
        isDraft: step?.status === "draft",
        wdkPushError: step?.wdkPushError ?? null,
      };
    }),
  );
}
