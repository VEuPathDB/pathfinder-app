"use client";

import { ChevronRight } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useId, useState, type ReactNode } from "react";

import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

const OPEN = { type: "spring", stiffness: 420, damping: 38 } as const;

interface FoldProps {
  title: string;
  meta?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}

export function Fold({
  title,
  meta,
  defaultOpen = false,
  className,
  children,
}: FoldProps) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const reveal = useEntrance({
    initial: { height: 0, opacity: 0 },
    exit: { height: 0, opacity: 0 },
    transition: OPEN,
  });
  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md py-1 text-left text-sm font-medium text-foreground transition-colors duration-120 hover:text-primary"
      >
        <span>{title}</span>
        <span className="flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
          {meta}
          <ChevronRight
            aria-hidden
            className={cn(
              "size-3.5 transition-transform duration-200 motion-reduce:transition-none",
              open && "rotate-90",
            )}
          />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            key="body"
            {...reveal}
            animate={{ height: "auto", opacity: 1 }}
            className="overflow-hidden"
          >
            <div className="pt-2">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
