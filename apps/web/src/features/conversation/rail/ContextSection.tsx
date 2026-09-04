"use client";

import { leadUsagePayloadSchema } from "@pathfinder/shared/generated/zod/leadUsagePayloadSchema";
import { subAgentCallPayloadSchema } from "@pathfinder/shared/generated/zod/subAgentCallPayloadSchema";
import type { UIMessage } from "ai";

import { phaseLabel } from "@/lib/models/phaseRoles";
import { cn } from "@/lib/utils/cn";
import { formatTokens } from "@/features/conversation/usageFormat";

import { LedgerRow, LedgerSection } from "./LedgerPanelPrimitives";

const LEAD_USAGE = "data-lead-usage";
const SUB_AGENT_CALL = "data-sub-agent-call";
const LEAD_KEY = "lead";

type Part = UIMessage["parts"][number];

interface ContextFill {
  key: string;
  label: string;
  tokens: number;
  window: number;
}

/**
 * One fill per agent that reported a request size: the Lead, plus each phase's
 * latest dispatch while it runs. A finished dispatch holds no context.
 */
function contextFills(parts: readonly Part[]): ContextFill[] {
  const byPhase = new Map<string, ContextFill>();
  let lead: ContextFill | null = null;
  for (const part of parts) {
    if (part.type === LEAD_USAGE) {
      const parsed = leadUsagePayloadSchema.safeParse(part.data);
      if (!parsed.success) continue;
      lead = {
        key: LEAD_KEY,
        label: phaseLabel(LEAD_KEY),
        tokens: parsed.data.contextTokens ?? 0,
        window: parsed.data.contextWindow ?? 0,
      };
      continue;
    }
    if (part.type !== SUB_AGENT_CALL) continue;
    const parsed = subAgentCallPayloadSchema.safeParse(part.data);
    if (!parsed.success) continue;
    const call = parsed.data;
    byPhase.delete(call.phase);
    if (call.state !== "started") continue;
    byPhase.set(call.phase, {
      key: call.phase,
      label: phaseLabel(call.phase),
      tokens: call.contextTokens ?? 0,
      window: call.contextWindow ?? 0,
    });
  }
  const rows = lead === null ? [...byPhase.values()] : [lead, ...byPhase.values()];
  return rows.filter((row) => row.tokens > 0);
}

function toneFor(pct: number): string {
  if (pct >= 0.95) return "bg-destructive";
  if (pct >= 0.8) return "bg-warning";
  return "bg-primary";
}

function ContextFillValue({ fill }: { fill: ContextFill }) {
  if (fill.window <= 0) {
    return (
      <span className="font-mono text-[10px] text-muted-foreground">
        {formatTokens(fill.tokens)}
      </span>
    );
  }
  const pct = Math.min(fill.tokens / fill.window, 1);
  return (
    <>
      <span className="font-mono text-[10px] text-muted-foreground">
        {`${formatTokens(fill.tokens)} / ${formatTokens(fill.window)}`}
      </span>
      <span
        role="progressbar"
        aria-label={`${fill.label} context window`}
        aria-valuemin={0}
        aria-valuemax={fill.window}
        aria-valuenow={fill.tokens}
        className="h-1 w-12 overflow-hidden rounded-full bg-muted"
      >
        <span
          data-testid={`context-fill-${fill.key}`}
          className={cn("block h-full transition-[width]", toneFor(pct))}
          style={{ width: `${Math.max(pct * 100, 2).toFixed(1)}%` }}
        />
      </span>
    </>
  );
}

export function ContextSection({ parts }: { parts: readonly Part[] }) {
  const fills = contextFills(parts);
  if (fills.length === 0) return null;
  return (
    <LedgerSection title="Context">
      {fills.map((fill) => (
        <LedgerRow
          key={fill.key}
          label={fill.label}
          value={<ContextFillValue fill={fill} />}
        />
      ))}
    </LedgerSection>
  );
}
