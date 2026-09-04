import ELK from "elkjs/lib/elk.bundled.js";
import type { Strategy } from "@pathfinder/shared";

const elk = new ELK();

const NODE_WIDTH = 224;
const NODE_HEIGHT = 112;
const GRID = 28;

export type StepPositions = Map<string, { x: number; y: number }>;

/**
 * Lays out a strategy DAG with ELK's layered algorithm.
 *
 * Uses FIXED_ORDER WEST ports on combine steps (primary port index 0, secondary
 * port index 1) so the primary-input source is placed visually above the
 * secondary-input source — the invariant dagre's `constraints` API previously
 * enforced.
 */
export async function layoutStrategyGraph(
  strategy: Strategy | null,
): Promise<StepPositions> {
  const positions: StepPositions = new Map();
  if (!strategy || strategy.steps.length === 0) return positions;

  const stepIds = new Set(strategy.steps.map((s) => s.id));
  const isCombineStep = (id: string): boolean => {
    const s = strategy.steps.find((st) => st.id === id);
    if (!s) return false;
    return s.primaryInputStepId != null && s.secondaryInputStepId != null;
  };

  const children = strategy.steps.map((step) => {
    const combine = isCombineStep(step.id);
    // ELK port.index on WEST side is counter-clockwise (bottom-up):
    // index 0 sits at the bottom, higher index toward the top. To place
    // the primary source VISUALLY ABOVE the secondary source (the WDK
    // convention), primary-in needs the higher index.
    const ports = combine
      ? [
          {
            id: `${step.id}:secondary-in`,
            properties: { "port.side": "WEST", "port.index": "0" },
          },
          {
            id: `${step.id}:primary-in`,
            properties: { "port.side": "WEST", "port.index": "1" },
          },
          {
            id: `${step.id}:out`,
            properties: { "port.side": "EAST", "port.index": "0" },
          },
        ]
      : [
          {
            id: `${step.id}:in`,
            properties: { "port.side": "WEST", "port.index": "0" },
          },
          {
            id: `${step.id}:out`,
            properties: { "port.side": "EAST", "port.index": "0" },
          },
        ];
    return {
      id: step.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      layoutOptions: { "elk.portConstraints": "FIXED_ORDER" },
      ports,
    };
  });

  const edges: Array<{ id: string; sources: string[]; targets: string[] }> = [];
  for (const step of strategy.steps) {
    if (step.primaryInputStepId != null && stepIds.has(step.primaryInputStepId)) {
      const targetPort = isCombineStep(step.id)
        ? `${step.id}:primary-in`
        : `${step.id}:in`;
      edges.push({
        id: `${step.primaryInputStepId}->${step.id}:primary`,
        sources: [`${step.primaryInputStepId}:out`],
        targets: [targetPort],
      });
    }
    if (step.secondaryInputStepId != null && stepIds.has(step.secondaryInputStepId)) {
      edges.push({
        id: `${step.secondaryInputStepId}->${step.id}:secondary`,
        sources: [`${step.secondaryInputStepId}:out`],
        targets: [`${step.id}:secondary-in`],
      });
    }
  }

  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.spacing.nodeNode": String(GRID * 2),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(GRID * 4),
      "elk.padding": `[top=${GRID * 2},right=${GRID * 2},bottom=${GRID * 2},left=${GRID * 2}]`,
    },
    children,
    edges,
  };

  const laidOut = await elk.layout(elkGraph);
  for (const child of laidOut.children ?? []) {
    positions.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
  }
  return positions;
}
