"use client";

import { motion, useMotionValue, useSpring, useTransform } from "motion/react";

import { usePrefersReducedMotion } from "@/lib/motion";

const TICK = { duration: 0.4, bounce: 0 } as const;

interface AnimatedCountProps {
  value: number;
  className?: string;
}

export function AnimatedCount({ value, className }: AnimatedCountProps) {
  const reduced = usePrefersReducedMotion();
  const target = useMotionValue(value);
  const eased = useSpring(target, TICK);
  const shown = useTransform(eased, (v) => Math.round(v).toLocaleString());
  if (target.get() !== value) target.set(value);
  if (reduced) {
    return (
      <span data-testid="animated-count" className={className}>
        {value.toLocaleString()}
      </span>
    );
  }
  return (
    <motion.span data-testid="animated-count" className={className}>
      {shown}
    </motion.span>
  );
}
