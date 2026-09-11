"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEntrance, usePrefersReducedMotion } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

const P_TOP = "140 35.74";
const P_BOT = "140 144.26";
const REGION_PATHS = {
  A: `M ${P_TOP} A 62 62 0 1 0 ${P_BOT} A 62 62 0 0 1 ${P_TOP} Z`,
  LENS: `M ${P_TOP} A 62 62 0 0 1 ${P_BOT} A 62 62 0 0 1 ${P_TOP} Z`,
  B: `M ${P_TOP} A 62 62 0 1 1 ${P_BOT} A 62 62 0 0 0 ${P_TOP} Z`,
} as const;

export type VennRegion = keyof typeof REGION_PATHS;

const COLOCATE_LEFT_CX = 58;
const COLOCATE_RIGHT_CX = 222;
const COLOCATE_R = 56;
const OVERLAP_LEFT_CX = 110;
const OVERLAP_RIGHT_CX = 170;
const OVERLAP_R = 62;
const SPRING = { type: "spring", stiffness: 220, damping: 26 } as const;

interface VennSvgProps {
  fillA: boolean;
  fillB: boolean;
  isRegionSelected: (region: VennRegion) => boolean;
  handleRegionClick: (region: VennRegion) => void;
  showA: string;
  showB: string;
  isColocate: boolean;
}

export function VennSvg({
  fillA,
  fillB,
  isRegionSelected,
  handleRegionClick,
  showA,
  showB,
  isColocate,
}: VennSvgProps) {
  const reduceMotion = usePrefersReducedMotion();
  const transition = reduceMotion ? { duration: 0 } : SPRING;
  const fadeEntrance = useEntrance({
    initial: { opacity: 0 },
    exit: { opacity: 0 },
    transition: { duration: 0.18 },
  });
  const arrowEntrance = useEntrance({
    initial: { opacity: 0, scale: 0.6 },
    exit: { opacity: 0, scale: 0.6 },
    transition: { duration: 0.25, delay: 0.12 },
  });
  const leftCx = isColocate ? COLOCATE_LEFT_CX : OVERLAP_LEFT_CX;
  const rightCx = isColocate ? COLOCATE_RIGHT_CX : OVERLAP_RIGHT_CX;
  const r = isColocate ? COLOCATE_R : OVERLAP_R;

  return (
    <svg
      viewBox="0 0 280 180"
      width="280"
      height="180"
      role="img"
      aria-label="Venn region picker"
      className="select-none"
    >
      <motion.circle
        cx={leftCx}
        cy="90"
        r={r}
        fill="hsl(var(--primary) / 0.55)"
        fillOpacity={fillA ? 1 : 0}
        animate={{ cx: leftCx, r, fillOpacity: fillA ? 1 : 0 }}
        transition={transition}
      />
      <motion.circle
        cx={rightCx}
        cy="90"
        r={r}
        fill="hsl(var(--primary) / 0.55)"
        fillOpacity={fillB ? 1 : 0}
        animate={{ cx: rightCx, r, fillOpacity: fillB ? 1 : 0 }}
        transition={transition}
      />

      <motion.circle
        cx={leftCx}
        cy="90"
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-muted-foreground"
        animate={{ cx: leftCx, r }}
        transition={transition}
      />
      <motion.circle
        cx={rightCx}
        cy="90"
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-muted-foreground"
        animate={{ cx: rightCx, r }}
        transition={transition}
      />

      <AnimatePresence>
        {!isColocate && (
          <motion.g key="regions" {...fadeEntrance} animate={{ opacity: 1 }}>
            <RegionPath
              label="A only"
              d={REGION_PATHS.A}
              selected={isRegionSelected("A")}
              onClick={() => handleRegionClick("A")}
            />
            <RegionPath
              label="Intersection region"
              d={REGION_PATHS.LENS}
              selected={isRegionSelected("LENS")}
              onClick={() => handleRegionClick("LENS")}
            />
            <RegionPath
              label="B only"
              d={REGION_PATHS.B}
              selected={isRegionSelected("B")}
              onClick={() => handleRegionClick("B")}
            />
          </motion.g>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isColocate && (
          <motion.g key="colocate-targets" {...fadeEntrance} animate={{ opacity: 1 }}>
            <RegionCircle
              label="A only"
              cx={leftCx}
              r={r}
              onClick={() => handleRegionClick("A")}
            />
            <RegionCircle
              label="B only"
              cx={rightCx}
              r={r}
              onClick={() => handleRegionClick("B")}
            />
          </motion.g>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isColocate && (
          <motion.g
            key="colocate-arrow"
            {...arrowEntrance}
            animate={{ opacity: 1, scale: 1 }}
            style={{ transformOrigin: "140px 90px", pointerEvents: "none" }}
          >
            <line
              x1={120}
              y1={90}
              x2={160}
              y2={90}
              stroke="hsl(var(--primary))"
              strokeWidth={2.5}
              strokeLinecap="round"
            />
            <path
              d="M125 84 L120 90 L125 96"
              stroke="hsl(var(--primary))"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            <path
              d="M155 84 L160 90 L155 96"
              stroke="hsl(var(--primary))"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </motion.g>
        )}
      </AnimatePresence>

      <motion.text
        x={leftCx - 50}
        y="170"
        textAnchor="middle"
        className="fill-muted-foreground text-xs"
        animate={{ x: leftCx - 50 }}
        transition={transition}
      >
        {showA}
      </motion.text>
      <motion.text
        x={rightCx + 50}
        y="170"
        textAnchor="middle"
        className="fill-muted-foreground text-xs"
        animate={{ x: rightCx + 50 }}
        transition={transition}
      >
        {showB}
      </motion.text>
    </svg>
  );
}

function RegionPath({
  label,
  d,
  selected,
  onClick,
}: {
  label: string;
  d: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <path
      d={d}
      role="button"
      aria-label={label}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{ pointerEvents: "all" }}
      className={cn(
        "cursor-pointer outline-none transition-[fill] duration-150 ease-[cubic-bezier(.4,0,.2,1)] focus-visible:stroke-ring focus-visible:stroke-2",
        selected
          ? "fill-[hsl(var(--primary)/0.55)] hover:fill-[hsl(var(--primary)/0.7)]"
          : "fill-transparent hover:fill-[hsl(var(--primary)/0.18)]",
      )}
    />
  );
}

function RegionCircle({
  label,
  cx,
  r,
  onClick,
}: {
  label: string;
  cx: number;
  r: number;
  onClick: () => void;
}) {
  return (
    <motion.circle
      cx={cx}
      cy={90}
      r={r}
      animate={{ cx, r }}
      transition={SPRING}
      role="button"
      aria-label={label}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{ pointerEvents: "all" }}
      className="cursor-pointer outline-none transition-[fill] duration-150 ease-[cubic-bezier(.4,0,.2,1)] fill-transparent hover:fill-[hsl(var(--primary)/0.18)] focus-visible:stroke-ring focus-visible:stroke-2"
    />
  );
}
