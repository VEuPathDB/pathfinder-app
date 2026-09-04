"use client";

import { CompactRowKebab } from "@/features/strategy/graph/components/CompactRowKebab";
import { VennIcon } from "@/features/strategy/graph/components/VennIcon";
import type { CompactStep } from "@/features/strategy/graph/utils/compactLayout";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { cn } from "@/lib/utils/cn";

const KIND_DOT: Record<string, string> = {
  search: "bg-[hsl(var(--kind-leaf))]",
  combine: "bg-[hsl(var(--kind-combine))]",
  transform: "bg-[hsl(var(--kind-transform))]",
};

export interface StepRowProps extends RowActions {
  step: CompactStep;
}

export interface RowActions {
  onStepClick?: (stepId: string) => void;
  selectedStepId?: string | null;
  onSaveStep?: (stepId: string) => void;
  onInsertSavedAt?: (stepId: string) => void;
}

export function CompactStepRow({
  step,
  onStepClick,
  selectedStepId = null,
  onSaveStep,
  onInsertSavedAt,
}: StepRowProps) {
  return (
    <div className="flex items-center gap-1">
      <StepRowButton
        step={step}
        selectedStepId={selectedStepId}
        {...(onStepClick !== undefined && { onStepClick })}
      />
      {(onSaveStep != null || onInsertSavedAt != null) && (
        <CompactRowKebab
          stepId={step.id}
          {...(onSaveStep !== undefined && { onSaveStep })}
          {...(onInsertSavedAt !== undefined && { onInsertSavedAt })}
        />
      )}
    </div>
  );
}

function StepRowButton({ step, onStepClick, selectedStepId = null }: StepRowProps) {
  const snapshot = useStepSnapshot(step.source);
  const liveCount = snapshot.estimatedSize;
  const isSelected = step.id === selectedStepId;
  const operator = step.kind === "combine" ? (step.operator ?? "") : "";
  // The inputs are listed directly beneath, so the row names the operation and
  // keeps the full expression for the tooltip.
  const label = operator === "" ? step.displayName : operatorName(operator);
  const title =
    operator === ""
      ? step.displayName
      : combineOperatorLabel(operator, step.operandNames);
  return (
    <button
      type="button"
      onClick={() => onStepClick?.(step.id)}
      data-testid={`compact-step-row-${step.id}`}
      aria-current={isSelected ? "true" : undefined}
      className={cn(
        isSelected && "bg-accent ring-1 ring-primary/50",
        "flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-sm transition-colors hover:bg-accent",
      )}
    >
      {/* One fixed-width column so every label starts at the same x and the
          indentation is what reads as hierarchy. */}
      <span aria-hidden className="flex w-4 shrink-0 items-center justify-start">
        {operator === "" ? (
          <span
            className={cn(
              "inline-block size-2 rounded-full",
              KIND_DOT[step.kind] ?? "bg-muted",
            )}
          />
        ) : (
          <VennIcon operator={operator} width={16} />
        )}
      </span>
      <span
        className="flex-1 truncate text-xs font-medium text-foreground"
        title={title}
      >
        {label}
      </span>
      <span className="text-[10px] tabular-nums text-muted-foreground">
        {typeof liveCount === "number" ? liveCount.toLocaleString() : "..."}
      </span>
    </button>
  );
}

const OPERATOR_NAME: Record<string, string> = {
  INTERSECT: "Intersect",
  UNION: "Union",
  MINUS: "Minus",
  RMINUS: "Minus (reversed)",
  LONLY: "Left only",
  RONLY: "Right only",
  COLOCATE: "Colocated",
};

function operatorName(operator: string): string {
  return OPERATOR_NAME[operator] ?? operator;
}

function combineOperatorLabel(operator: string, operands?: [string, string]): string {
  const [a, b] = operands ?? ["A", "B"];
  switch (operator) {
    case "INTERSECT":
      return `${a} ∩ ${b}`;
    case "UNION":
      return `${a} ∪ ${b}`;
    case "MINUS":
      return `${a} - ${b}`;
    case "RMINUS":
      return `${b} - ${a}`;
    case "LONLY":
      return `${a} only`;
    case "RONLY":
      return `${b} only`;
    case "COLOCATE":
      return `${a} near ${b}`;
    default:
      return operator;
  }
}
