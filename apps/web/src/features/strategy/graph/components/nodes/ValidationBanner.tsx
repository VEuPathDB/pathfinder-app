"use client";

import type { Step } from "@pathfinder/shared";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";

export type ValidationBannerProps = {
  step: Step;
  snapshot: StepSnapshot;
  onOpenDetails?: ((stepId: string) => void) | undefined;
};

/** Whichever failure the step is carrying, or null when it is healthy. */
export function stepErrorMessage(snapshot: StepSnapshot): string | null {
  // A WDK rejection shows even when the lifecycle machine is idle: the push
  // failed on the server, so nothing local transitions to "invalid".
  if (!snapshot.isInvalid && !snapshot.isFailed && snapshot.wdkPushError == null) {
    return null;
  }
  return (
    snapshot.wdkPushError ??
    snapshot.validationErrors?.general?.[0] ??
    snapshot.lastError ??
    "Validation error"
  );
}

/**
 * The error lives behind the corner dot. Printing it on the node pushed the
 * name and the count out of the way, which is when a reader needs them most.
 */
export function ValidationBanner({
  step,
  snapshot,
  onOpenDetails,
}: ValidationBannerProps) {
  const message = stepErrorMessage(snapshot);
  if (message == null) return null;

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          data-testid="node-error-trigger"
          aria-label={message}
          onClick={(event) => {
            event.stopPropagation();
            onOpenDetails?.(step.id);
          }}
          className="absolute -left-1 -top-1 z-20 h-4 w-4 rounded-full"
        >
          <span
            data-corner-dot="error"
            className="absolute -left-1 -top-1 z-10 h-2.5 w-2.5 rounded-full bg-destructive ring-2 ring-background"
          />
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        data-testid="node-error-content"
        align="start"
        side="top"
        className="w-80 border-destructive/30 bg-card text-xs text-destructive"
      >
        <div className="mb-1.5 font-semibold">This step cannot run</div>
        <p className="max-h-40 overflow-auto break-words font-normal text-foreground">
          {message}
        </p>
        {onOpenDetails != null && (
          <span className="mt-1.5 block text-[10px] text-muted-foreground">
            Click the dot for details.
          </span>
        )}
      </HoverCardContent>
    </HoverCard>
  );
}
