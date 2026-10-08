"use client";

import { useQuery } from "@tanstack/react-query";
import { getMyQuotaQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyQuota";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatCost, formatTokens } from "@/features/conversation/usageFormat";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { cn } from "@/lib/utils/cn";

type MeterTone = "neutral" | "warning" | "exhausted";

const TONE_STROKE: Record<MeterTone, string> = {
  neutral: "stroke-primary",
  warning: "stroke-warning",
  exhausted: "stroke-destructive",
};

export function meterTone(pct: number): MeterTone {
  if (pct >= 1) return "exhausted";
  if (pct >= 0.8) return "warning";
  return "neutral";
}

function formatResetsAt(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function RailQuotaMeter({ siteId }: { siteId: string }) {
  const { data: authStatus } = useQuery({
    ...authStatusOptions(siteId),
    retryOnMount: false,
  });
  // The quota read needs a session. Asking without one is refused with 401.
  const { data } = useQuery({
    ...getMyQuotaQueryOptions(),
    enabled: authStatus?.signedIn === true,
  });
  if (data == null) return null;

  const used = Number(data.usedUsd);
  const limit = Number(data.limitUsd);
  const pct = limit > 0 ? Math.min(used / limit, 1) : 0;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label="Monthly spend"
          tabIndex={0}
          className="flex size-9 items-center justify-center rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <svg width={28} height={28} viewBox="0 0 28 28" aria-hidden>
            <circle
              cx={14}
              cy={14}
              r={10}
              fill="none"
              strokeWidth={3}
              className="stroke-border"
            />
            <circle
              data-testid="quota-ring-fill"
              cx={14}
              cy={14}
              r={10}
              fill="none"
              strokeWidth={3}
              strokeLinecap="round"
              pathLength={100}
              strokeDasharray={`${pct * 100} 100`}
              transform="rotate(-90 14 14)"
              className={cn(
                "transition-[stroke-dasharray]",
                TONE_STROKE[meterTone(pct)],
              )}
            />
          </svg>
        </span>
      </TooltipTrigger>
      <TooltipContent side="right" className="space-y-0.5">
        <div className="text-muted-foreground">
          Account total this month, across all conversations.
        </div>
        <div>{`${formatCost(used)} of ${formatCost(limit)} this month`}</div>
        <div>{`${formatTokens(data.totalTokens)} tokens, resets ${formatResetsAt(data.resetsAt)}`}</div>
        {data.ownKeyProviders.length > 0 && (
          <div>
            {`On your keys this month: ${formatCost(Number(data.ownKeyUsd))}, ${formatTokens(data.ownKeyTokens)} tokens`}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
