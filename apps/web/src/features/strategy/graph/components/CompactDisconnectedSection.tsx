"use client";

import type { Step, Strategy } from "@pathfinder/shared";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useDeleteOperation } from "@/features/strategy/graph/hooks/useDeleteOperation";
import { inferStepKind } from "@/features/strategy/graph";
import { cn } from "@/lib/utils/cn";

const KIND_DOT: Record<string, string> = {
  search: "bg-[hsl(var(--kind-leaf))]",
  combine: "bg-[hsl(var(--kind-combine))]",
  transform: "bg-[hsl(var(--kind-transform))]",
};

interface DisconnectedSectionProps {
  strategy: Strategy;
  orphans: Step[];
  onStepClick?: (stepId: string) => void;
  selectedStepId?: string | null;
}

export function CompactDisconnectedSection({
  strategy,
  orphans,
  onStepClick,
  selectedStepId = null,
}: DisconnectedSectionProps) {
  const deleteOp = useDeleteOperation(strategy.id);
  const handleClear = () => {
    deleteOp.requestDeleteMany(
      orphans.map((s) => s.id),
      { skipConfirm: true },
    );
  };
  return (
    <section
      data-testid="compact-strategy-orphans"
      className="rounded-md border border-dashed border-warning/40 bg-warning/10 p-2"
    >
      <header className="mb-1 flex items-center justify-between gap-2 px-1 text-[10px] uppercase tracking-wide text-warning">
        <span>{orphans.length} disconnected</span>
        <Button
          type="button"
          size="xs"
          variant="ghost"
          onClick={handleClear}
          className="h-5 gap-1 px-1.5 text-[10px] text-warning hover:text-warning"
        >
          <Trash2 className="size-3" aria-hidden /> Remove all
        </Button>
      </header>
      <p className="px-1 pb-1 text-[10px] text-muted-foreground">
        These steps aren&apos;t connected and block save. Remove or wire them up in the
        full editor.
      </p>
      <ol className="flex flex-col gap-0.5">
        {orphans.map((step) => (
          <OrphanRow
            key={step.id}
            step={step}
            isSelected={step.id === selectedStepId}
            {...(onStepClick !== undefined && { onStepClick })}
          />
        ))}
      </ol>
    </section>
  );
}

interface OrphanRowProps {
  step: Step;
  onStepClick?: (stepId: string) => void;
  isSelected?: boolean;
}

function OrphanRow({ step, onStepClick, isSelected = false }: OrphanRowProps) {
  const kind = inferStepKind(step);
  const dot = KIND_DOT[kind] ?? "bg-muted";
  const displayName = step.displayName ?? step.searchName ?? step.id;
  return (
    <li>
      <button
        type="button"
        onClick={() => onStepClick?.(step.id)}
        data-testid={`compact-orphan-row-${step.id}`}
        className={cn(
          isSelected && "bg-accent ring-1 ring-primary/50",
          "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs hover:bg-accent",
        )}
      >
        <span
          aria-hidden
          className={cn("inline-block size-2 shrink-0 rounded-full", dot)}
        />
        <span className="flex-1 truncate">{displayName}</span>
      </button>
    </li>
  );
}
