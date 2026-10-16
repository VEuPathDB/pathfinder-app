"use client";

import { CircleAlert } from "lucide-react";
import type { ReactElement } from "react";
import type { TurnFacts } from "@pathfinder/shared";

export function DataFactsNotices({ data }: { data: TurnFacts }): ReactElement | null {
  const lines = [
    { testId: "facts-stopped-check", text: data.stoppedCheck ?? "" },
    { testId: "facts-refusal", text: data.refusal ?? "" },
  ].filter((line) => line.text !== "");
  if (lines.length === 0) return null;
  return (
    <div data-testid="facts-notice" className="space-y-1">
      {lines.map((line) => (
        <div
          key={line.testId}
          data-testid={line.testId}
          className="flex items-start gap-2 text-xs text-muted-foreground"
        >
          <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>{line.text}</span>
        </div>
      ))}
    </div>
  );
}
