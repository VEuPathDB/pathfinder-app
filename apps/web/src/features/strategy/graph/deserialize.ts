import type { Edge, Node } from "@xyflow/react";
import { MarkerType, Position } from "@xyflow/react";
import type { Step, Strategy } from "@pathfinder/shared";
import { walkSubtreeIds } from "@/features/strategy/operations";
import { hslFromTriple } from "@/lib/color/hsl";
import { inferStepKind } from "./kind";
import type { StepPositions } from "./layout";

export interface EdgeColors {
  border: string;
  foreground: string;
  card: string;
  mutedForeground: string;
}

/** An unresolved ink role inherits the color of the text around the canvas. */
const UNRESOLVED_INK = "currentColor";

/** An unresolved surface role paints nothing. */
const UNRESOLVED_SURFACE = "transparent";

/** The canvas paint for one deserialization, read once from the ground. */
export function readEdgeColors(): EdgeColors {
  const style =
    typeof document === "undefined" ? null : getComputedStyle(document.documentElement);
  const read = (variable: string, fallback: string): string => {
    if (style === null) return fallback;
    const raw = style.getPropertyValue(variable).trim();
    return raw === "" ? fallback : hslFromTriple(raw);
  };
  return {
    border: read("--border", UNRESOLVED_INK),
    foreground: read("--foreground", UNRESOLVED_INK),
    card: read("--card", UNRESOLVED_SURFACE),
    mutedForeground: read("--muted-foreground", UNRESOLVED_INK),
  };
}

type ExistingPositions = Map<string, { x: number; y: number }>;
type DeserializeOptions = {
  /**
   * Fresh layout positions (ELK). Used for nodes without an existing position
   * and - when `forceRelayout` is set - for every node.
   */
  computedPositions?: StepPositions;
  /**
   * User-moved positions preserved across re-renders. Takes precedence over
   * `computedPositions` unless `forceRelayout` is true.
   */
  existingPositions?: ExistingPositions;
  /** Ignore existing positions and relayout from `computedPositions`. */
  forceRelayout?: boolean;
};

export function deserializeStrategyToGraph(
  strategy: Strategy | null,
  onOpenDetails?: (stepId: string) => void,
  options?: DeserializeOptions,
): { nodes: Node[]; edges: Edge[] } {
  if (!strategy || strategy.steps.length === 0) {
    return { nodes: [], edges: [] };
  }

  const colors = readEdgeColors();
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const stepMap = new Map<string, Step>();
  const usedAsInputCount = new Map<string, number>();

  for (const step of strategy.steps) {
    stepMap.set(step.id, step);
  }
  for (const step of strategy.steps) {
    if (step.primaryInputStepId != null) {
      usedAsInputCount.set(
        step.primaryInputStepId,
        (usedAsInputCount.get(step.primaryInputStepId) ?? 0) + 1,
      );
    }
    if (step.secondaryInputStepId != null) {
      usedAsInputCount.set(
        step.secondaryInputStepId,
        (usedAsInputCount.get(step.secondaryInputStepId) ?? 0) + 1,
      );
    }
  }
  const rootStepIds = strategy.steps
    .map((s) => s.id)
    .filter((id) => (usedAsInputCount.get(id) ?? 0) === 0);
  const rootSet = new Set(rootStepIds);
  const shouldShowRootOutputs = rootStepIds.length !== 1;

  // Match serialize: prefer Strategy.rootStepId when it is still a real root,
  // else fall back to the unique root if any. Anything not reachable from the
  // chosen root is an orphan and rendered with an "isOrphan" tag.
  let chosenRoot: string | null = null;
  if (
    strategy.rootStepId != null &&
    strategy.rootStepId !== "" &&
    stepMap.has(strategy.rootStepId) &&
    rootSet.has(strategy.rootStepId)
  ) {
    chosenRoot = strategy.rootStepId;
  } else if (rootStepIds.length === 1) {
    chosenRoot = rootStepIds[0]!;
  }
  const reachable =
    chosenRoot != null
      ? new Set(walkSubtreeIds(strategy.steps, chosenRoot))
      : new Set<string>();

  const gridSize = 28;
  const snap = (value: number) => Math.round(value / gridSize) * gridSize;

  const computed: StepPositions =
    options?.computedPositions ?? new Map<string, { x: number; y: number }>();
  const existing: ExistingPositions | undefined =
    options?.forceRelayout === true ? undefined : options?.existingPositions;

  // Normalize computed positions so minX/minY respect the gridSize margin.
  const allComputed = Array.from(computed.values());
  let offsetX = 0;
  let offsetY = 0;
  if (allComputed.length > 0) {
    const minX = Math.min(...allComputed.map((p) => p.x));
    const minY = Math.min(...allComputed.map((p) => p.y));
    offsetX = minX < gridSize * 2 ? gridSize * 2 - minX : 0;
    offsetY = minY < gridSize * 2 ? gridSize * 2 - minY : 0;
  }

  // When preserving, anchor the computed frame onto the existing frame using
  // the first node that appears in both.
  let translateX = 0;
  let translateY = 0;
  if (existing) {
    for (const step of strategy.steps) {
      const ex = existing.get(step.id);
      const cp = computed.get(step.id);
      if (ex && cp) {
        translateX = ex.x - snap(cp.x + offsetX);
        translateY = ex.y - snap(cp.y + offsetY);
        break;
      }
    }
  }

  for (const [stepIndex, step] of strategy.steps.entries()) {
    const kind = inferStepKind(step);
    const ex = existing ? existing.get(step.id) : null;
    const cp = computed.get(step.id);
    const finalPos =
      ex ??
      (cp
        ? {
            x: snap(cp.x + offsetX + translateX),
            y: snap(cp.y + offsetY + translateY),
          }
        : undefined);
    if (!finalPos) continue;
    nodes.push({
      id: step.id,
      type: "step",
      position: {
        x: finalPos.x,
        y: finalPos.y,
      },
      data: {
        step,
        onOpenDetails,
        isOrphan: !reachable.has(step.id),
        showOutputHandle: shouldShowRootOutputs && rootSet.has(step.id),
        showPrimaryInputHandle:
          (kind === "transform" || kind === "combine") &&
          step.primaryInputStepId == null,
        showSecondaryInputHandle:
          kind === "combine" && step.secondaryInputStepId == null,
        enterDelayIndex: stepIndex,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });

    if (step.primaryInputStepId != null) {
      if (!stepMap.has(step.primaryInputStepId)) continue;
      const hasSecondary = step.secondaryInputStepId != null;
      const primaryEdge: Edge = {
        id: `${step.primaryInputStepId}-${step.id}-primary`,
        source: step.primaryInputStepId,
        target: step.id,
        sourceHandle: "right",
        targetHandle: "left",
        type: "step",
        style: { stroke: colors.border, strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: colors.border,
          width: 14,
          height: 14,
        },
      };
      if (hasSecondary) {
        primaryEdge.label = "L (primary)";
        primaryEdge.labelStyle = {
          fontSize: 11,
          fontWeight: 700,
          fill: colors.foreground,
        };
        primaryEdge.labelBgStyle = {
          fill: colors.card,
          stroke: colors.border,
          strokeWidth: 1,
        };
        primaryEdge.labelBgPadding = [6, 2];
        primaryEdge.labelBgBorderRadius = 6;
      }
      edges.push(primaryEdge);
    }

    if (step.secondaryInputStepId != null) {
      if (!stepMap.has(step.secondaryInputStepId)) continue;
      edges.push({
        id: `${step.secondaryInputStepId}-${step.id}-secondary`,
        source: step.secondaryInputStepId,
        target: step.id,
        sourceHandle: "right",
        targetHandle: "left-secondary",
        type: "step",
        label: "R (secondary)",
        labelStyle: { fontSize: 11, fontWeight: 700, fill: colors.foreground },
        labelBgStyle: { fill: colors.card, stroke: colors.border, strokeWidth: 1 },
        labelBgPadding: [6, 2],
        labelBgBorderRadius: 6,
        style: { stroke: colors.mutedForeground, strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: colors.mutedForeground,
          width: 14,
          height: 14,
        },
      });
    }
  }

  return { nodes, edges };
}
