"use client";

import { Circle, CircleAlert, CircleX, Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import type { ReviewTone, Verdict } from "./reviewModel";

const TONE_SURFACE: Record<ReviewTone, string> = {
  good: "bg-success/10",
  warn: "bg-warning/10",
  bad: "bg-destructive/10",
  neutral: "bg-muted",
};

const TONE_ICON: Record<ReviewTone, string> = {
  good: "text-success",
  warn: "text-warning",
  bad: "text-destructive",
  neutral: "text-muted-foreground",
};

function DrawnCheck() {
  const draw = useEntrance({
    initial: { pathLength: 0 },
    transition: { duration: 0.3, ease: "easeOut", delay: 0.08 },
  });
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" aria-hidden>
      <motion.path
        d="M20 6 9 17l-5-5"
        stroke="currentColor"
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
        {...draw}
        animate={{ pathLength: 1 }}
      />
    </svg>
  );
}

function VerdictIcon({ verdict }: { verdict: Verdict }) {
  if (verdict.tone === "good") return <DrawnCheck />;
  if (verdict.tone === "warn") return <CircleAlert className="size-4" aria-hidden />;
  if (verdict.tone === "bad") return <CircleX className="size-4" aria-hidden />;
  if (verdict.kind === "working") {
    return <Loader2 className="size-4 animate-spin" aria-hidden />;
  }
  return <Circle className="size-4" aria-hidden />;
}

export function ReviewVerdict({ verdict }: { verdict: Verdict }) {
  const swap = useEntrance({
    initial: { opacity: 0, y: 4 },
    exit: { opacity: 0, y: -4 },
    transition: { duration: 0.16 },
  });
  return (
    <div role="status" data-testid="review-verdict">
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={verdict.kind}
          {...swap}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            "flex items-start gap-2.5 rounded-lg px-3 py-2.5",
            TONE_SURFACE[verdict.tone],
          )}
        >
          <span className={cn("mt-0.5 shrink-0", TONE_ICON[verdict.tone])}>
            <VerdictIcon verdict={verdict} />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">{verdict.title}</p>
            {verdict.detail !== null && (
              <p className="text-xs leading-relaxed text-muted-foreground">
                {verdict.detail}
              </p>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
