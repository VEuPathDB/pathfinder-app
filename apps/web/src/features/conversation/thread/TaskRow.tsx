"use client";

import { Check, X } from "lucide-react";
import type { ReactElement } from "react";

export type TaskOutcome = "running" | "success" | "failure";

export interface TaskRowProps {
  label: string;
  percent: number | null;
  message: string | null;
  estimatedSeconds: number | null;
  outcome: TaskOutcome;
  error: string | null;
  /** In-page link to the turn that carries what the task produced. */
  resultHref?: string | null;
}

function amountOf(outcome: TaskOutcome, pct: number): string {
  if (outcome === "success") return "Completed";
  if (outcome === "failure") return "Failed";
  return `${String(pct)}%`;
}

function Badge({ outcome, pct }: { outcome: TaskOutcome; pct: number }): ReactElement {
  if (outcome === "success")
    return <Check className="size-5 text-success" aria-hidden />;
  if (outcome === "failure")
    return <X className="size-5 text-destructive" aria-hidden />;
  return (
    <span
      className="size-5 shrink-0 rounded-full"
      style={{
        background: `conic-gradient(var(--color-primary) ${String(pct)}%, var(--color-muted) 0)`,
      }}
      aria-hidden
    />
  );
}

export function TaskRow({
  label,
  percent,
  message,
  estimatedSeconds,
  outcome,
  error,
  resultHref = null,
}: TaskRowProps): ReactElement {
  const pct = Math.round((percent ?? 0) * 100);
  const running = outcome === "running";
  return (
    <div data-testid="task-row">
      <div className="flex h-8 items-center gap-2">
        <Badge outcome={outcome} pct={pct} />
        <span className="truncate text-[13px] text-foreground">{label}</span>
        {running && estimatedSeconds !== null && (
          <span
            data-testid="task-row-elapsed"
            className="text-xs text-muted-foreground"
          >
            ~{estimatedSeconds} s
          </span>
        )}
        <span
          data-testid="task-row-status"
          className="ml-auto text-xs text-muted-foreground tabular-nums"
        >
          {amountOf(outcome, pct)}
        </span>
        {resultHref !== null && (
          <a
            href={resultHref}
            data-testid="task-row-result-link"
            className="text-xs font-medium text-primary underline-offset-2 hover:underline"
          >
            View result
          </a>
        )}
      </div>
      <div data-testid="data-task-progress" className="text-xs">
        {running && message !== null && (
          <div className="text-muted-foreground">{message}</div>
        )}
        <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted">
          <div
            data-testid="progress-bar-fill"
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${String(pct)}%` }}
          />
        </div>
      </div>
      {outcome === "failure" && error !== null && (
        <p className="mt-1 text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
