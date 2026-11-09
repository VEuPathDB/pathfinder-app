"use client";

import { threadUsage, type ThreadUsage } from "@veupathdb/assistant-client";
import { motion } from "motion/react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import { useChatHelpers } from "../runtime/chatHelpersContext";
import { formatCost, formatTokens, formatUsage } from "../usageFormat";
import { leadContextFill, type ContextFill } from "./contextFill";

const RADIUS = 7;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function tone(share: number): string {
  if (share >= 0.95) return "text-destructive";
  if (share >= 0.8) return "text-warning";
  return "text-primary";
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

function RingDetail({ fill, usage }: { fill: ContextFill | null; usage: ThreadUsage }) {
  return (
    <div className="space-y-1 text-xs">
      {fill !== null && (
        <Row
          label="Assistant context"
          value={`${formatTokens(fill.tokens)} of ${formatTokens(fill.window)}`}
        />
      )}
      <div className="border-t border-border/60 pt-1 text-muted-foreground">
        This conversation&apos;s total across all turns.
      </div>
      <Row
        label="Assistant"
        value={formatUsage(usage.lead.tokens, usage.lead.costUsd)}
      />
      <Row
        label="Sub-agents"
        value={formatUsage(usage.subAgents.tokens, usage.subAgents.costUsd)}
      />
      <div className="font-medium">
        Conversation · {formatTokens(usage.total.tokens)} tokens ·{" "}
        {formatCost(usage.total.costUsd)}
      </div>
    </div>
  );
}

export function ContextRing() {
  const messages = useChatHelpers().messages;
  const usage = threadUsage(messages);
  const fill = leadContextFill(messages.flatMap((m) => m.parts));
  const share = fill === null ? 0 : Math.min(fill.tokens / fill.window, 1);
  const draw = useEntrance({
    initial: { strokeDashoffset: CIRCUMFERENCE },
    transition: { duration: 0.5 },
  });
  if (fill === null && usage.total.tokens === 0 && usage.total.costUsd === 0)
    return null;
  const label =
    fill === null
      ? "Conversation usage"
      : `Assistant context ${Math.round(share * 100)}% full`;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip tapToOpen>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="context-ring"
            aria-label={label}
            className={cn(
              "inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-1.5 transition-colors duration-120 hover:bg-muted max-[900px]:min-h-11",
              tone(share),
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
            {fill !== null && (
              <span className="text-xs tabular-nums text-muted-foreground">
                {Math.round(share * 100)}%
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">
          <RingDetail fill={fill} usage={usage} />
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
