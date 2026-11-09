"use client";

import { motion, type Variants } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils/cn";

export const REVIEW_LIST: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.04 } },
};

export const REVIEW_ITEM: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.18, ease: "easeOut" } },
};

interface ReviewSectionProps {
  title?: string;
  meta?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function ReviewSection({
  title,
  meta,
  className,
  children,
}: ReviewSectionProps) {
  return (
    <motion.section
      layout="position"
      variants={REVIEW_ITEM}
      className={cn(
        "flex flex-col gap-2.5 border-b border-border px-4 py-4",
        className,
      )}
    >
      {title !== undefined && (
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {meta !== undefined && (
            <span className="text-xs text-muted-foreground">{meta}</span>
          )}
        </div>
      )}
      {children}
    </motion.section>
  );
}
