"use client";

import { useState } from "react";
import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Bookmark } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { insertSavedStrategy } from "@/lib/api/conversations";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { refetchStrategy } from "@/lib/api/strategy";
import type { InsertSavedRequest } from "@pathfinder/shared/generated/types/InsertSavedRequest";
import { toUserMessage } from "@/lib/api/errors";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { cn } from "@/lib/utils/cn";
import { COMBINE_OP_LABELS } from "@pathfinder/shared";

type Operator = NonNullable<InsertSavedRequest["operator"]>;

const OPERATORS: readonly Operator[] = ["INTERSECT", "UNION", "MINUS", "RMINUS"];

/** The operator a select reports, or the default when it names none. */
function operatorOf(value: string): Operator {
  return OPERATORS.find((op) => op === value) ?? "INTERSECT";
}

interface InsertSavedDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversationId: string;
  siteId: string;
  /** The step to combine with; empty when the strategy has no steps yet. */
  targetStepId: string;
}

export function InsertSavedDialog(props: InsertSavedDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent data-testid="insert-saved-dialog" className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Insert saved strategy</DialogTitle>
          <DialogDescription>
            {props.targetStepId === ""
              ? "Pick a saved strategy from your library. Its steps become this strategy's first steps, and you can keep building from there."
              : "Pick a saved strategy from your library and choose how it should combine with the target step. The inserted strategy renders as a collapsed container in the strategy view."}
          </DialogDescription>
        </DialogHeader>
        <QueryBoundary>
          <InsertSavedDialogBody {...props} />
        </QueryBoundary>
      </DialogContent>
    </Dialog>
  );
}

function InsertSavedDialogBody({
  conversationId,
  siteId,
  targetStepId,
  onOpenChange,
}: InsertSavedDialogProps) {
  const queryClient = useQueryClient();
  const { data: convs } = useSuspenseQuery(listStrategiesQueryOptions({ siteId }));
  const saved = convs
    .filter(
      (c) => c.isSaved === true && c.wdkStrategyId != null && c.id !== conversationId,
    )
    .sort((a, b) => a.name.localeCompare(b.name));

  const [filter, setFilter] = useState("");
  const [pickedId, setPickedId] = useState<number | null>(null);
  const [operator, setOperator] = useState<Operator>("INTERSECT");

  const filtered =
    filter.trim() === ""
      ? saved
      : saved.filter((c) => c.name.toLowerCase().includes(filter.trim().toLowerCase()));

  const isRoot = targetStepId === "";
  const insert = useMutation({
    mutationFn: () =>
      insertSavedStrategy({
        conversationId,
        siteId,
        targetStepId,
        savedWdkStrategyId: pickedId ?? 0,
        operator: isRoot ? undefined : operator,
      }),
    onSuccess: (data) => {
      void refetchStrategy(queryClient, conversationId);
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      toast.success("Saved strategy inserted", {
        description: data.insertedSavedName,
      });
      onOpenChange(false);
    },
    onError: (e) => toast.error("Insert failed", { description: toUserMessage(e) }),
  });

  return (
    <div className="space-y-3">
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter saved strategies..."
        className="h-8 w-full rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="max-h-72 overflow-auto rounded-md border border-border">
        {filtered.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">
            No saved strategies yet - save one from a step&apos;s &ldquo;Save as
            reusable&rdquo; menu first.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setPickedId(c.wdkStrategyId ?? null)}
                  className={cn(
                    "flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-muted/50",
                    pickedId === c.wdkStrategyId && "bg-primary/10",
                  )}
                  data-testid={`insert-saved-pick-${c.wdkStrategyId}`}
                >
                  <Bookmark
                    className="mt-0.5 size-3 shrink-0 text-primary"
                    aria-hidden
                  />
                  <span className="flex-1">
                    <span className="block text-sm font-medium">{c.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {c.stepCount ?? 0} {(c.stepCount ?? 0) === 1 ? "step" : "steps"}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!isRoot && (
        <div className="flex items-center gap-2">
          <label
            htmlFor="insert-saved-operator"
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
          >
            Operator
          </label>
          <select
            id="insert-saved-operator"
            value={operator}
            onChange={(e) => setOperator(operatorOf(e.target.value))}
            className="h-8 flex-1 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            {OPERATORS.map((op) => (
              <option key={op} value={op}>
                {COMBINE_OP_LABELS[op]}
              </option>
            ))}
          </select>
        </div>
      )}
      <DialogFooter>
        <Button
          type="button"
          variant="ghost"
          onClick={() => onOpenChange(false)}
          disabled={insert.isPending}
        >
          Cancel
        </Button>
        <Button
          type="button"
          onClick={() => insert.mutate()}
          disabled={pickedId == null || insert.isPending}
          data-testid="insert-saved-confirm"
        >
          {insert.isPending ? "Sending..." : "Insert"}
        </Button>
      </DialogFooter>
    </div>
  );
}
