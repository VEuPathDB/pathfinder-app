"use client";

import { useQuery } from "@tanstack/react-query";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getMyQuotaQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { cn } from "@/lib/utils/cn";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const currencySubCent = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

function formatUsed(value: number): string {
  if (value <= 0) return currency.format(0);
  if (value < 0.01) return currencySubCent.format(value);
  return currency.format(value);
}

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatResetsAt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const PILL_CLASS =
  "flex items-center gap-2 rounded-full px-2.5 py-1 text-[11px] font-medium drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]";
const NEUTRAL_TONE = "bg-white/15 text-white ring-1 ring-white/30";

export function QuotaPill({ siteId }: { siteId: string }) {
  const { data: authStatus } = useQuery(authStatusOptions(siteId));
  // The quota read needs a session. Asking without one is refused with 401.
  const { data } = useQuery({
    ...getMyQuotaQueryOptions(),
    enabled: authStatus?.signedIn === true,
  });
  if (data == null) return null;

  const used = Number(data.usedUsd);
  const limit = Number(data.limitUsd);
  const resets = formatResetsAt(data.resetsAt);

  if (data.ownKeyProviders.length > 0) {
    const own = Number(data.ownKeyUsd);
    return (
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              aria-label="Spend on your keys"
              tabIndex={0}
              className={cn(PILL_CLASS, NEUTRAL_TONE)}
            >
              <span>{formatUsed(own)}</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            On your keys this month: {formatUsed(own)},{" "}
            {compact.format(data.ownKeyTokens)} tokens. PathFinder allowance:{" "}
            {formatUsed(used)} of {currency.format(limit)}. Resets {resets}.
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  const pct = limit > 0 ? Math.min(used / limit, 1) : 0;

  const tone =
    pct >= 1
      ? "bg-destructive/30 text-white ring-1 ring-destructive/50"
      : pct >= 0.8
        ? "bg-warning/30 text-white ring-1 ring-warning/50"
        : NEUTRAL_TONE;

  const barColor =
    pct >= 1 ? "bg-destructive" : pct >= 0.8 ? "bg-warning" : "bg-white/80";

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div aria-label="Monthly quota" tabIndex={0} className={cn(PILL_CLASS, tone)}>
            <span>
              {formatUsed(used)} / {currency.format(limit)}
            </span>
            <span
              data-testid="quota-bar"
              className="h-1 w-12 overflow-hidden rounded-full bg-black/30"
            >
              <span
                className={cn("block h-full transition-[width]", barColor)}
                style={{ width: `${Math.max(pct * 100, 2)}%` }}
              />
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="space-y-0.5">
          <div className="text-muted-foreground">
            Account total this month, across all conversations.
          </div>
          <div>
            {compact.format(data.totalTokens)} tokens · resets {resets}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
