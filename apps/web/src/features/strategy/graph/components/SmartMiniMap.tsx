"use client";

import { motion } from "motion/react";
import { MiniMap } from "@xyflow/react";
import type { StepKind } from "@strategist/shared";
import { useCanvasIdle } from "@/features/strategy/graph/hooks/useCanvasIdle";
import { hslFromTriple } from "@/lib/color/hsl";

const MINIMAP_NODE_TOKEN: Record<StepKind, string> = {
  search: "--kind-leaf",
  combine: "--kind-combine",
  transform: "--kind-transform",
};

const MINIMAP_MASK_COLOR = "hsl(var(--foreground) / 0.1)";

/** Resolved paint for one minimap node. An empty token means no stylesheet. */
export function minimapNodeColor(node: {
  data?: { step?: { kind?: string } };
}): string {
  const kind = node.data?.step?.kind;
  const token =
    kind === "search" || kind === "combine" || kind === "transform"
      ? MINIMAP_NODE_TOKEN[kind]
      : "--muted-foreground";
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return raw === "" ? "currentColor" : hslFromTriple(raw);
}

interface SmartMiniMapProps {
  /** Total node count. The minimap is hidden when this is 8 or less. */
  nodeCount: number;
  /** Idle threshold in ms. Defaults to 3000. */
  idleMs?: number;
}

export function SmartMiniMap({ nodeCount, idleMs = 3000 }: SmartMiniMapProps) {
  const idle = useCanvasIdle({ idleMs });
  if (nodeCount <= 8) return null;

  return (
    <motion.div
      data-testid="smart-mini-map"
      animate={{ opacity: idle ? 0.2 : 1 }}
      transition={{ duration: 0.2 }}
      whileHover={{ opacity: 1 }}
    >
      <MiniMap
        nodeColor={minimapNodeColor}
        maskColor={MINIMAP_MASK_COLOR}
        className="rounded-lg border border-border bg-card"
      />
    </motion.div>
  );
}
