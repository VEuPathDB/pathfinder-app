"use client";

import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import { motion, type MotionProps, type MotionStyle } from "motion/react";
import { type ComponentType, type ElementType, type JSX, memo, useMemo } from "react";

type MotionHTMLProps = MotionProps & Record<string, unknown>;

const motionComponentCache = new Map<
  keyof JSX.IntrinsicElements,
  ComponentType<MotionHTMLProps>
>();

function getMotionComponent(element: keyof JSX.IntrinsicElements) {
  const existing = motionComponentCache.get(element);
  if (existing !== undefined) return existing;
  const created = motion.create(element) as ComponentType<MotionHTMLProps>;
  motionComponentCache.set(element, created);
  return created;
}

export type TextShimmerProps = {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
};

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
  spread = 2,
}: TextShimmerProps) => {
  const MotionComponent = getMotionComponent(Component as keyof JSX.IntrinsicElements);

  const dynamicSpread = useMemo(
    () => (children?.length ?? 0) * spread,
    [children, spread],
  );
  const entrance = useEntrance({
    initial: { backgroundPosition: "100% center" },
    transition: {
      repeat: Number.POSITIVE_INFINITY,
      duration,
      ease: "linear",
    },
  });

  return (
    <MotionComponent
      {...entrance}
      animate={{ backgroundPosition: "0% center" }}
      className={cn(
        "relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent",
        "[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-background),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]",
        className,
      )}
      style={
        {
          "--spread": `${dynamicSpread}px`,
          backgroundImage:
            "var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))",
        } as MotionStyle
      }
    >
      {children}
    </MotionComponent>
  );
};

export const Shimmer = memo(ShimmerComponent);
