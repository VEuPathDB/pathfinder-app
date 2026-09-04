import type { Patch } from "immer";
import type { Strategy } from "@pathfinder/shared";
import type { GraphOperation } from "@/lib/types/graphOperation";
import type {
  StepLifecycleSeed,
  StepMachineEvent,
  StepMachineSnapshot,
} from "./stepMachine";

interface FailedOperationPayload {
  op: GraphOperation;
}

interface DraftState {
  lastFailedOperation: FailedOperationPayload | null;
  setLastFailedOperation: (payload: FailedOperationPayload | null) => void;
  clear: () => void;
}

export interface LifecycleSlice {
  /** Per-step XState v5 machine snapshot. Pure reducer, no running actors. */
  stepLifecycleById: Record<string, StepMachineSnapshot>;

  /** Ensure a lifecycle entry exists for the given step id. No-op if already present. */
  initStepLifecycle: (stepId: string, seed?: StepLifecycleSeed) => void;
  /** Dispatch an event to the step's machine. Auto-initializes if missing. */
  dispatchStepEvent: (stepId: string, event: StepMachineEvent) => void;
  /** Remove the lifecycle entry for a step id. */
  removeStepLifecycle: (stepId: string) => void;
  /** Read-only snapshot accessor. Returns null if no entry exists. */
  getStepLifecycle: (stepId: string) => StepMachineSnapshot | null;

  /** Apply validation results for a batch of steps (error message or cleared). */
  applyStepValidationErrors: (errors: Record<string, string | undefined>) => void;
  /** Apply count results for a batch of steps (number, null, or undefined). */
  applyStepCounts: (counts: Record<string, number | null | undefined>) => void;
}

export interface HistorySnapshot {
  strategy: Strategy | null;
}

export interface HistorySlice {
  undoStack: Patch[][];
  redoStack: Patch[][];

  pushSnapshot: (prev: HistorySnapshot, current: Strategy | null) => void;
  /** Apply the most recent inverse patch to *current* and return the resulting
   *  strategy. Returns null if the undo stack is empty. */
  undo: (current: Strategy | null) => Strategy | null;
  /** Apply the most recent forward patch to *current* and return the resulting
   *  strategy. Returns null if the redo stack is empty. */
  redo: (current: Strategy | null) => Strategy | null;
  canUndo: () => boolean;
  canRedo: () => boolean;
  clearHistory: () => void;
}

interface MetaState {
  graphValidationStatus: Record<string, boolean>;

  setGraphValidationStatus: (id: string, hasErrors: boolean) => void;
}

// ---------------------------------------------------------------------------
// Combined store type
// ---------------------------------------------------------------------------

export type StrategyState = DraftState & HistorySlice & MetaState & LifecycleSlice;
