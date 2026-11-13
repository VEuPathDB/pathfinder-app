"use client";

import { useAuiState } from "@assistant-ui/react";
import {
  threadModeEnum,
  type ThreadMode,
} from "@strategist/shared/generated/types/ThreadMode";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { THREAD_MODE_DESCRIPTIONS, THREAD_MODE_LABELS } from "@/lib/threadModes";
import { useThreadModeStore } from "@/state/useThreadModeStore";

import { useThreadMode } from "./threadMode";

const THREAD_MODES: readonly ThreadMode[] = Object.values(threadModeEnum);

function isThreadMode(value: string): value is ThreadMode {
  return THREAD_MODES.some((mode) => mode === value);
}

export function ModeSwitch({ conversationId }: { conversationId: string }) {
  const mode = useThreadMode(conversationId);
  const setMode = useThreadModeStore((s) => s.setMode);
  const isRunning = useAuiState((s) => s.thread.isRunning);
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      aria-label="Mode"
      data-testid="mode-switch"
      value={mode}
      disabled={isRunning}
      onValueChange={(next) => {
        if (isThreadMode(next)) setMode(conversationId, next);
      }}
    >
      {THREAD_MODES.map((option) => (
        <ToggleGroupItem
          key={option}
          value={option}
          title={THREAD_MODE_DESCRIPTIONS[option]}
          className="px-3 text-xs max-[900px]:min-h-11"
        >
          {THREAD_MODE_LABELS[option]}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
