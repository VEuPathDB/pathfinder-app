"use client";

import { AlertTriangle } from "lucide-react";
import type { Step } from "@pathfinder/shared";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { getZeroResultSuggestions } from "@/features/strategy/validation/zeroResultAdvisor";

interface ZeroResultHoverCardProps {
  step: Step;
  count: number | null;
}

export function ZeroResultHoverCard({ step, count }: ZeroResultHoverCardProps) {
  if (count !== 0) return null;
  const suggestions = getZeroResultSuggestions(step);

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          data-testid="zero-result-trigger"
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold text-warning hover:bg-warning/10"
        >
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          <span>0 results</span>
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        data-testid="zero-result-content"
        align="center"
        side="top"
        className="w-64 border-warning/40 bg-card text-xs text-warning"
      >
        <div className="mb-1.5 font-semibold">0 results - try:</div>
        <ul className="list-disc space-y-1 pl-4">
          {suggestions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </HoverCardContent>
    </HoverCard>
  );
}
