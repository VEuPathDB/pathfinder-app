"use client";

import { useRef, useState } from "react";

export type StepDraftValues = Record<string, unknown>;

export function stepDraftKey(strategyId: string, stepId: string): string {
  return `pathfinder.editor.draft.${strategyId}.${stepId}`;
}

function readStorage(key: string): StepDraftValues | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null || raw === "") return null;
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return parsed as StepDraftValues;
  } catch {
    return null;
  }
}

function writeStorage(key: string, values: StepDraftValues): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(values));
  } catch {
    /* quota exceeded - surface nothing */
  }
}

function clearStorage(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export interface UseStepDraftPersistenceArgs {
  strategyId: string;
  stepId: string;
  /** Throttle interval for writes. Default 100ms. */
  throttleMs?: number;
}

export interface StepDraftPersistence {
  loadDraft: () => StepDraftValues | null;
  scheduleWrite: (values: StepDraftValues) => void;
  clear: () => void;
  flush: () => void;
}

export function useStepDraftPersistence(
  args: UseStepDraftPersistenceArgs,
): StepDraftPersistence {
  const { strategyId, stepId, throttleMs = 100 } = args;
  const key = stepDraftKey(strategyId, stepId);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<StepDraftValues | null>(null);

  const flush = (): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingRef.current !== null) {
      writeStorage(key, pendingRef.current);
      pendingRef.current = null;
    }
  };

  const scheduleWrite = (values: StepDraftValues): void => {
    pendingRef.current = values;
    if (timerRef.current !== null) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (pendingRef.current !== null) {
        writeStorage(key, pendingRef.current);
        pendingRef.current = null;
      }
    }, throttleMs);
  };

  const clear = (): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRef.current = null;
    clearStorage(key);
  };

  const loadDraft = (): StepDraftValues | null => readStorage(key);

  return { loadDraft, scheduleWrite, clear, flush };
}

export interface UseRecoveredDraftArgs {
  strategyId: string;
  stepId: string;
  baselineValues: StepDraftValues;
}

export interface RecoveredDraft {
  draft: StepDraftValues | null;
  dismiss: () => void;
}

function shallowEqualValues(a: StepDraftValues, b: StepDraftValues): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  for (const k of aKeys) {
    const av = a[k];
    const bv = b[k];
    if (Array.isArray(av) && Array.isArray(bv)) {
      if (av.length !== bv.length) return false;
      for (let i = 0; i < av.length; i += 1) {
        if (av[i] !== bv[i]) return false;
      }
    } else if (av !== bv) {
      return false;
    }
  }
  return true;
}

export function useRecoveredDraft(args: UseRecoveredDraftArgs): RecoveredDraft {
  const key = stepDraftKey(args.strategyId, args.stepId);
  const [dismissed, setDismissed] = useState(false);

  const stored = readStorage(key);
  const draft =
    stored !== null && !shallowEqualValues(stored, args.baselineValues) ? stored : null;

  return {
    draft: dismissed ? null : draft,
    dismiss: () => {
      clearStorage(key);
      setDismissed(true);
    },
  };
}
