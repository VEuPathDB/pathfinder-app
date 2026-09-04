"use client";

import type { ReactElement } from "react";
import type { TraceGroupState } from "@pathfinder/assistant-client";

import { phaseLabel } from "@/lib/models/phaseRoles";
import { formatUsage } from "@/features/conversation/usageFormat";

import { TraceRow } from "./TraceRow";
import type { TraceGroupView } from "./traceTypes";

const LEAD = "lead";

/** What a reader reads for a dispatch its turn never resolved. */
function stateLabel(state: TraceGroupState): string | null {
  if (state === "cancelled") return "Stopped";
  if (state === "superseded") return "Not finished";
  return null;
}

/** What a reader reads for a call the same turn left without a result. */
function stoppedLabel(state: TraceGroupState): string {
  return state === "cancelled" ? "Stopped" : "Not finished";
}

export interface TraceGroupProps {
  group: TraceGroupView;
  bare: boolean;
  showRaw: boolean;
  showUsage: boolean;
  nameFor: (toolName: string) => string;
  labelFor?: (phase: string) => string;
}

export function TraceGroup({
  group,
  bare,
  showRaw,
  showUsage,
  nameFor,
  labelFor,
}: TraceGroupProps): ReactElement {
  const rows = group.rows.map((row) => (
    <TraceRow
      key={row.key}
      row={row}
      showRaw={showRaw}
      nameFor={nameFor}
      stoppedLabel={stoppedLabel(group.state)}
    />
  ));
  if (bare) return <div>{rows}</div>;
  const label = (labelFor ?? phaseLabel)(group.phase);
  const usage = showUsage && group.tokens > 0;
  const outcome = stateLabel(group.state);
  return (
    <div data-testid={group.key === LEAD ? undefined : "data-sub-agent-call"}>
      <div data-testid="trace-group" className="flex h-6 items-center gap-2">
        <span
          data-testid="trace-group-label"
          className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
        >
          {label}
        </span>
        {outcome !== null && (
          <span
            data-testid="trace-group-state"
            className="text-[11px] text-muted-foreground"
          >
            {outcome}
          </span>
        )}
        {usage && (
          <span
            data-testid="trace-group-usage"
            className="text-[11px] text-muted-foreground tabular-nums"
          >
            {formatUsage(group.tokens, group.costUsd)}
          </span>
        )}
      </div>
      <div className="border-l border-border/50 pl-3">{rows}</div>
    </div>
  );
}
