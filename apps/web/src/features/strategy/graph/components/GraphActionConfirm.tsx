"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { OperationChoice } from "@/features/strategy/operations";
import { cn } from "@/lib/utils/cn";

interface GraphActionConfirmProps<R extends string> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Headline shown above the choices (e.g. "Delete this step?"). */
  title: string;
  /** Optional subtext (e.g. step display name). */
  subtitle?: string | undefined;
  choices: OperationChoice<R>[];
  /** Called with the chosen resolution token. */
  onConfirm: (resolution: R) => void;
  /** Optional verb for the confirm button label. Defaults to "Apply". */
  confirmLabel?: string | undefined;
}

export function GraphActionConfirm<R extends string>({
  open,
  onOpenChange,
  title,
  subtitle,
  choices,
  onConfirm,
  confirmLabel = "Apply",
}: GraphActionConfirmProps<R>) {
  const initial =
    choices.find((c) => c.isDefault)?.resolution ?? choices[0]?.resolution;
  const [selected, setSelected] = useState<R | undefined>(initial);
  const [trackedChoices, setTrackedChoices] = useState(choices);

  if (trackedChoices !== choices) {
    setTrackedChoices(choices);
    setSelected(initial);
  }

  const handleConfirm = (): void => {
    if (selected === undefined) return;
    onConfirm(selected);
    onOpenChange(false);
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="graph-action-confirm" className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {subtitle !== undefined && subtitle !== "" && (
            <AlertDialogDescription>{subtitle}</AlertDialogDescription>
          )}
        </AlertDialogHeader>

        <RadioGroup
          value={selected ?? ""}
          onValueChange={(v) => setSelected(v as R)}
          className="flex flex-col gap-2 py-2"
        >
          {choices.map((choice) => {
            const id = `graph-confirm-${choice.resolution}`;
            const isActive = selected === choice.resolution;
            return (
              <label
                key={choice.resolution}
                htmlFor={id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-md border p-3 text-left transition-colors",
                  isActive
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-input hover:bg-accent",
                )}
              >
                <RadioGroupItem id={id} value={choice.resolution} className="mt-1" />
                <div className="flex flex-1 flex-col gap-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{choice.title}</span>
                    {choice.isDefault && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[0.625rem] font-medium uppercase tracking-wide text-muted-foreground">
                        default
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {choice.description}
                  </span>
                  <span className="text-[0.6875rem] text-muted-foreground">
                    Will delete {choice.willDelete.length}
                  </span>
                </div>
              </label>
            );
          })}
        </RadioGroup>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            data-testid="graph-action-confirm-apply"
            disabled={selected === undefined}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
