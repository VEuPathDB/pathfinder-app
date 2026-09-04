"use client";

import { ChevronRight } from "lucide-react";
import { useState, type ReactElement, type ReactNode } from "react";

import { cn } from "@/lib/utils/cn";
import { formatUsage } from "@/features/conversation/usageFormat";

import { TraceGroup } from "./TraceGroup";
import type { TraceGroupView } from "./traceTypes";

export interface TraceRunView {
  groups: TraceGroupView[];
  rowCount: number;
  running: boolean;
}

/** The turn's model and its whole-turn totals, for the summary row. */
export interface TraceUsageView {
  model: string;
  tokens: number;
  costUsd: string;
}

export interface TraceProps {
  run: TraceRunView;
  showRaw: boolean;
  showUsage: boolean;
  usage?: TraceUsageView;
  labelFor?: (phase: string) => string;
  nameFor: (toolName: string) => string;
  approval?: ReactNode;
}

const LEAD = "lead";

function summaryOf(run: TraceRunView): string {
  const rows = run.groups.flatMap((group) => group.rows);
  if (rows.some((row) => row.status === "running")) return "Working...";
  if (rows.some((row) => row.status === "awaiting-approval")) return "Waiting for you";
  return run.rowCount === 1 ? "1 step" : `${run.rowCount} steps`;
}

function usageLine(usage: TraceUsageView): string {
  return `${usage.model} - ${formatUsage(usage.tokens, usage.costUsd)}`;
}

/** A turn the Lead ran alone needs no heading over its one group. */
function isBare(groups: readonly TraceGroupView[]): boolean {
  const only = groups.length === 1 ? groups[0] : undefined;
  return only?.key === LEAD;
}

export function Trace({
  run,
  showRaw,
  showUsage,
  usage,
  labelFor,
  nameFor,
  approval,
}: TraceProps): ReactElement {
  // A trace that mounts mid-run starts open; one that mounts settled starts
  // closed. After mount only the reader's toggle changes it.
  const [open, setOpen] = useState(run.running);
  // The rows leave the accessibility and hit-testing tree only once the
  // collapse has finished, so the animation has something to animate.
  const [furled, setFurled] = useState(!run.running);
  const bare = isBare(run.groups);
  const toggle = () => {
    if (!open) setFurled(false);
    setOpen(!open);
  };
  return (
    <div data-testid="turn-trace">
      <button
        type="button"
        data-testid="turn-trace-toggle"
        aria-expanded={open}
        onClick={toggle}
        className="flex h-7 w-full items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight
          className={cn("size-3 shrink-0 transition-transform", open && "rotate-90")}
          aria-hidden
        />
        <span data-testid="turn-trace-summary">{summaryOf(run)}</span>
        {showUsage && usage !== undefined && (
          <span
            data-testid="trace-usage"
            title="This turn"
            className="ml-auto font-mono text-[11px] tabular-nums"
          >
            {usageLine(usage)}
          </span>
        )}
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
        onTransitionEnd={() => {
          if (!open) setFurled(true);
        }}
      >
        <div
          className="overflow-hidden"
          style={{ visibility: furled && !open ? "hidden" : "visible" }}
        >
          {run.groups.map((group, index) => (
            <TraceGroup
              key={`${group.key}-${String(index)}`}
              group={group}
              bare={bare}
              showRaw={showRaw}
              showUsage={showUsage}
              nameFor={nameFor}
              {...(labelFor === undefined ? {} : { labelFor })}
            />
          ))}
        </div>
      </div>
      {approval}
    </div>
  );
}
