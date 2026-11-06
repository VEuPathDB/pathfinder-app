"use client";

import { useAuiState } from "@assistant-ui/react";

import {
  THREAD_MODE_DESCRIPTIONS,
  THREAD_MODE_LABELS,
  nextThreadMode,
} from "@/lib/threadModes";
import { useThreadModeStore } from "@/state/useThreadModeStore";

import { useThreadMode } from "./threadMode";

export function ModePill({ conversationId }: { conversationId: string }) {
  const mode = useThreadMode(conversationId);
  const setMode = useThreadModeStore((s) => s.setMode);
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const label = THREAD_MODE_LABELS[mode];
  return (
    <button
      type="button"
      data-testid="mode-pill"
      aria-label={`Mode: ${label}`}
      title={THREAD_MODE_DESCRIPTIONS[mode]}
      disabled={isRunning}
      onClick={() => setMode(conversationId, nextThreadMode(mode))}
      className="inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
    >
      {label}
    </button>
  );
}
