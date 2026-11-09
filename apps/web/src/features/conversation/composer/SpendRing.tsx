"use client";

import { useQuery } from "@tanstack/react-query";
import { threadUsage } from "@veupathdb/assistant-client";
import { motion } from "motion/react";
import { getMyQuotaQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyQuota";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import { useSessionStore } from "@/state/useSessionStore";

import { useChatHelpers } from "../runtime/chatHelpersContext";
import { formatCost, formatTokens } from "../usageFormat";

const RADIUS = 7;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ringTone(share: number): string {
  if (share >= 1) return "text-destructive";
  if (share >= 0.8) return "text-warning";
  return "text-primary";
}

function spendLine(tokens: number, costUsd: number): string {
  return `${formatTokens(tokens)} tokens, ${formatCost(costUsd)}`;
}

function formatResetsAt(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function Row({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="flex justify-between gap-4">
      <span className="opacity-70">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export function SpendRing() {
  const siteId = useSessionStore((s) => s.selectedSite);
  const { data: authStatus } = useQuery({
    ...authStatusOptions(siteId),
    retryOnMount: false,
  });
  const { data: quota } = useQuery({
    ...getMyQuotaQueryOptions(),
    enabled: authStatus?.signedIn === true,
  });
  const usage = threadUsage(useChatHelpers().messages);
  const draw = useEntrance({
    initial: { strokeDashoffset: CIRCUMFERENCE },
    transition: { duration: 0.5 },
  });
  const spent = usage.total.tokens > 0 || Number(usage.total.costUsd) > 0;
  if (quota == null && !spent) return null;

  const used = Number(quota?.usedUsd ?? 0);
  const limit = Number(quota?.limitUsd ?? 0);
  const share = limit > 0 ? Math.min(used / limit, 1) : 0;
  const percent = Math.round(share * 100);
  const label =
    quota == null
      ? "This conversation's spend"
      : `Monthly spend ${percent}% of allowance`;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip tapToOpen>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="spend-ring"
            aria-label={label}
            className={cn(
              "inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-1.5 transition-colors duration-120 hover:bg-muted max-[900px]:min-h-11",
              ringTone(share),
            )}
          >
            <svg viewBox="0 0 20 20" className="size-4 -rotate-90" aria-hidden>
              <circle
                cx="10"
                cy="10"
                r={RADIUS}
                fill="none"
                strokeWidth="2.5"
                className="stroke-border"
              />
              <motion.circle
                cx="10"
                cy="10"
                r={RADIUS}
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeDasharray={CIRCUMFERENCE}
                {...draw}
                animate={{ strokeDashoffset: CIRCUMFERENCE * (1 - share) }}
              />
            </svg>
            {quota != null && (
              <span className="text-xs tabular-nums text-muted-foreground">
                {percent}%
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">
          <div className="min-w-48 space-y-1 text-xs">
            <Row
              testId="spend-conversation"
              label="This conversation"
              value={spendLine(usage.total.tokens, Number(usage.total.costUsd))}
            />
            {quota != null && (
              <>
                <Row
                  testId="spend-month"
                  label="This month"
                  value={`${formatCost(used)} of ${formatCost(limit)}`}
                />
                <Row
                  testId="spend-resets"
                  label="Resets"
                  value={formatResetsAt(quota.resetsAt)}
                />
                {quota.ownKeyProviders.length > 0 && (
                  <Row
                    testId="spend-own-keys"
                    label="On your keys"
                    value={`${formatCost(Number(quota.ownKeyUsd))}, ${formatTokens(quota.ownKeyTokens)} tokens`}
                  />
                )}
              </>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
