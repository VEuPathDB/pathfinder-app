"use client";

import { TriangleAlert } from "lucide-react";

interface UnreadableStateProps {
  reason: string;
}

export function UnreadableState({ reason }: UnreadableStateProps) {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center"
      data-testid="strategy-unreadable-state"
    >
      <div className="text-muted-foreground">
        <TriangleAlert className="h-12 w-12" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">
          This strategy could not be read
        </p>
        <p className="text-xs text-muted-foreground">
          Its stored plan does not load, so no step can be shown or built on: {reason}
        </p>
      </div>
    </div>
  );
}
