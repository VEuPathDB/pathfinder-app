"use client";

import { TriangleAlert } from "lucide-react";
import type { CombineMismatchGroup } from "@/features/strategy/graph";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface ValidationAlertProps {
  /** Combine groups whose member steps have mismatched record types. */
  mismatchGroups: CombineMismatchGroup[];
  /** Hard-fail flag from `graphValidationStatus[strategyId]`. */
  isPaused: boolean;
  /**
   * Called with the id of the first offending step. Caller is responsible for
   * scrolling that step into view via `fitView` and for opening its editor.
   */
  onView: (firstOffendingStepId: string) => void;
}

function pickFirstOffendingId(groups: CombineMismatchGroup[]): string | null {
  for (const group of groups) {
    for (const id of group.ids) {
      return id;
    }
  }
  return null;
}

function offendingCount(groups: CombineMismatchGroup[]): number {
  let count = 0;
  for (const g of groups) count += g.ids.size;
  return count;
}

export function ValidationAlert({
  mismatchGroups,
  isPaused,
  onView,
}: ValidationAlertProps) {
  const visible = mismatchGroups.length > 0 || isPaused;
  if (!visible) return null;

  const firstId = pickFirstOffendingId(mismatchGroups);
  const count = offendingCount(mismatchGroups);

  return (
    <Alert
      variant="destructive"
      data-testid="validation-alert"
      className="pointer-events-auto w-auto max-w-2xl border-warning/40 bg-warning/10 text-warning *:data-[slot=alert-description]:text-warning [&>svg]:text-warning"
    >
      <TriangleAlert className="size-4" aria-hidden />
      <AlertTitle className="flex items-center justify-between gap-3">
        <span>
          {count > 0 ? `${count} steps have mismatched record types.` : "Sync paused."}
        </span>
        {firstId !== null && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onView(firstId)}
            className="h-7 px-2 text-warning hover:bg-warning/15 hover:text-warning"
          >
            View →
          </Button>
        )}
      </AlertTitle>
      <AlertDescription>Sync is paused until resolved.</AlertDescription>
    </Alert>
  );
}
