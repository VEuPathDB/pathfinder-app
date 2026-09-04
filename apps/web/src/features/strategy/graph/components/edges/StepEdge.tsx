"use client";

import { motion } from "motion/react";
import { type EdgeProps, getSmoothStepPath } from "@xyflow/react";
import { usePrefersReducedMotion } from "@/features/strategy/graph/usePrefersReducedMotion";
import { EDGE_DRAW_DURATION_MS } from "@/features/strategy/graph/motion";

const STROKE_WIDTH = 1.5;
const INTERACTION_WIDTH = 24;
const STROKE_COLOR = "currentColor";

export function StepEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
  } = props;

  const reduced = usePrefersReducedMotion();
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      {/* Transparent wide hit area so the edge is clickable along its length,
          not just on the 1.5px visible stroke (which is unreliable to hit). */}
      <path
        d={path}
        data-testid={`step-edge-hit-${id}`}
        fill="none"
        stroke="transparent"
        strokeWidth={INTERACTION_WIDTH}
        className="cursor-pointer"
      />
      <motion.path
        id={id}
        d={path}
        data-testid={`step-edge-${id}`}
        data-label-x={labelX}
        data-label-y={labelY}
        fill="none"
        stroke={STROKE_COLOR}
        strokeWidth={STROKE_WIDTH}
        markerEnd={markerEnd}
        className="pointer-events-none text-muted-foreground"
        initial={reduced ? { pathLength: 1 } : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        exit={reduced ? { pathLength: 1 } : { pathLength: 0 }}
        transition={{
          duration: reduced ? 0 : EDGE_DRAW_DURATION_MS / 1000,
          ease: "easeOut",
        }}
      />
    </>
  );
}
