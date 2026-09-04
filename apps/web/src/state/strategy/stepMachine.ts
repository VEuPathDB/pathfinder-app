import {
  assign,
  createMachine,
  getInitialSnapshot,
  getNextSnapshot,
  type SnapshotFrom,
} from "xstate";
import type { ValidationErrors } from "@pathfinder/shared";

export interface StepMachineContext {
  estimatedSize: number | null;
  validationErrors: ValidationErrors | null;
  lastError: string | null;
}

export const STEP_LIFECYCLE_STATE_NAMES = [
  "idle",
  "validating",
  "valid",
  "invalid",
  "running",
  "complete",
  "failed",
] as const;

export type StepLifecycleStateName = (typeof STEP_LIFECYCLE_STATE_NAMES)[number];

export type StepMachineEvent =
  | { type: "VALIDATE" }
  | { type: "VALIDATION_SUCCESS"; estimatedSize?: number | null }
  | { type: "VALIDATION_ERROR"; errors: ValidationErrors }
  | { type: "RUN_COUNTS" }
  | { type: "COUNTS_READY"; count: number | null }
  | { type: "RUN_ERROR"; message: string }
  | { type: "RESET" };

const INITIAL_CONTEXT: StepMachineContext = {
  estimatedSize: null,
  validationErrors: null,
  lastError: null,
};

export const stepMachine = createMachine({
  // Stryker disable next-line StringLiteral: inspector label only, no behavior
  id: "step",
  initial: "idle",
  types: {
    context: {} as StepMachineContext,
    events: {} as StepMachineEvent,
  },
  context: INITIAL_CONTEXT,
  on: {
    RESET: {
      target: ".idle",
      actions: assign(() => ({ ...INITIAL_CONTEXT })),
    },
  },
  states: {
    idle: {
      on: {
        VALIDATE: { target: "validating" },
      },
    },
    validating: {
      on: {
        VALIDATION_SUCCESS: {
          target: "valid",
          actions: assign({
            validationErrors: () => null,
            lastError: () => null,
            estimatedSize: ({ context, event }) =>
              event.estimatedSize !== undefined
                ? event.estimatedSize
                : context.estimatedSize,
          }),
        },
        VALIDATION_ERROR: {
          target: "invalid",
          actions: assign({
            validationErrors: ({ event }) => event.errors,
          }),
        },
        RUN_ERROR: {
          target: "failed",
          actions: assign({
            lastError: ({ event }) => event.message,
          }),
        },
      },
    },
    valid: {
      on: {
        VALIDATE: { target: "validating" },
        RUN_COUNTS: { target: "running" },
      },
    },
    invalid: {
      on: {
        VALIDATE: { target: "validating" },
      },
    },
    running: {
      on: {
        COUNTS_READY: {
          target: "complete",
          actions: assign({
            estimatedSize: ({ event }) => event.count,
            lastError: () => null,
          }),
        },
        RUN_ERROR: {
          target: "failed",
          actions: assign({
            lastError: ({ event }) => event.message,
          }),
        },
      },
    },
    complete: {
      on: {
        VALIDATE: { target: "validating" },
        RUN_COUNTS: { target: "running" },
      },
    },
    failed: {
      on: {
        VALIDATE: { target: "validating" },
        RUN_COUNTS: { target: "running" },
      },
    },
  },
});

export type StepMachineSnapshot = SnapshotFrom<typeof stepMachine>;

export interface StepLifecycleSeed {
  state?: StepLifecycleStateName;
  context?: Partial<StepMachineContext>;
}

function emptyInitialSnapshot(): StepMachineSnapshot {
  return getInitialSnapshot(stepMachine, undefined);
}

export function seedStepMachine(
  state: StepLifecycleStateName,
  context?: Partial<StepMachineContext>,
): StepMachineSnapshot {
  const base = emptyInitialSnapshot();
  return {
    ...base,
    value: state,
    context: { ...INITIAL_CONTEXT, ...context },
  };
}

export function initialStepSnapshot(seed?: StepLifecycleSeed): StepMachineSnapshot {
  if (seed?.state !== undefined) {
    return seedStepMachine(seed.state, seed.context);
  }
  const base = emptyInitialSnapshot();
  if (seed?.context) {
    return { ...base, context: { ...base.context, ...seed.context } };
  }
  return base;
}

export function transitionStep(
  snapshot: StepMachineSnapshot,
  event: StepMachineEvent,
): StepMachineSnapshot {
  return getNextSnapshot(stepMachine, snapshot, event);
}
