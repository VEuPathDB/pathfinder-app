"use client";

import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import { TextAreaRow, TextRow } from "./ParamRows";
import { SelectRow } from "./SelectRow";
import type { Command, ParamDef, ParamValues } from "./types";

export interface ParamStepperProps {
  open: boolean;
  command: Command | null;
  onComplete: (values: ParamValues) => void;
  onCancel: () => void;
}

export function ParamStepper({
  open,
  command,
  onComplete,
  onCancel,
}: ParamStepperProps) {
  const [stepIdx, setStepIdx] = useState(0);
  const [values, setValues] = useState<ParamValues>({});
  const [lastOpen, setLastOpen] = useState(open);
  const entrance = useEntrance({
    initial: { opacity: 0, y: 6 },
    exit: { opacity: 0, y: 6 },
    transition: { duration: 0.15 },
  });

  // Render-time reset: when the stepper closes we clear state for the next
  // open without firing an effect after paint.
  if (lastOpen !== open) {
    setLastOpen(open);
    if (!open) {
      setStepIdx(0);
      setValues({});
    }
  }

  if (!open || command === null) return null;
  if (command.params.length === 0) return null;

  const param = command.params[stepIdx];
  if (param === undefined) return null;

  const isLast = stepIdx === command.params.length - 1;

  const next = (value: string) => {
    const merged = { ...values, [param.name]: value };
    setValues(merged);
    if (isLast) {
      onComplete(merged);
    } else {
      setStepIdx(stepIdx + 1);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        key="param-stepper"
        {...entrance}
        animate={{ opacity: 1, y: 0 }}
        data-testid="slash-param-stepper"
        className={cn(
          "absolute bottom-full left-0 right-0 z-20 mb-2",
          "rounded-lg border border-border bg-popover",
          "shadow-[var(--shadow-float)]",
        )}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono font-medium text-foreground">
              /{command.name}
            </span>
            <span className="text-muted-foreground">
              step {stepIdx + 1} / {command.params.length}
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            onClick={onCancel}
            aria-label="Cancel"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <ParamRow key={param.name} param={param} onSubmit={next} />
      </motion.div>
    </AnimatePresence>
  );
}

function ParamRow({
  param,
  onSubmit,
}: {
  param: ParamDef;
  onSubmit: (value: string) => void;
}) {
  if (param.kind === "select") {
    return <SelectRow param={param} onSubmit={onSubmit} />;
  }
  if (param.kind === "textarea") {
    return <TextAreaRow param={param} onSubmit={onSubmit} />;
  }
  return <TextRow param={param} onSubmit={onSubmit} />;
}
