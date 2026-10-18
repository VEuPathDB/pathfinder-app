"use client";

import type { ReactElement } from "react";
import { taskLifecycle, type TaskProgress } from "@veupathdb/assistant-client";
import { z } from "zod";
import { COMBINE_OP_LABELS } from "@pathfinder/shared";

import { useChatHelpers } from "../../runtime/chatHelpersContext";

const laneSchema = z.object({ candidateId: z.string() });

const searchSchema = z.object({
  displayName: z.string(),
  basis: z.string(),
  recovered: z.number().optional(),
  admitted: z.number().optional(),
  refused: z.string().optional(),
});

type Search = z.infer<typeof searchSchema>;

type SketchNode =
  | { kind: "leaf"; candidateId: string }
  | {
      kind: "combine";
      operator: "INTERSECT" | "UNION" | "MINUS";
      inputs: SketchNode[];
    };

const nodeSchema: z.ZodType<SketchNode> = z.lazy(() =>
  z.union([
    z.object({ kind: z.literal("leaf"), candidateId: z.string() }),
    z.object({
      kind: z.literal("combine"),
      operator: z.enum(["INTERSECT", "UNION", "MINUS"]),
      inputs: z.array(nodeSchema),
    }),
  ]),
);

const runSchema = z.object({ tree: nodeSchema });

function laneOf(progress: TaskProgress): string | null {
  return laneSchema.safeParse(progress.toolSpecific).data?.candidateId ?? null;
}

function titleOf(search: Search): string {
  return `${search.displayName}: ${search.basis}`;
}

function countsOf(search: Search): string {
  if (search.refused !== undefined) return "refused by the site";
  return `${String(search.recovered ?? 0)} positives, ${String(search.admitted ?? 0)} negatives`;
}

function SketchTree({
  node,
  searches,
}: {
  node: SketchNode;
  searches: ReadonlyMap<string, Search>;
}): ReactElement {
  if (node.kind === "leaf") {
    const search = searches.get(node.candidateId);
    return <li>{search === undefined ? node.candidateId : titleOf(search)}</li>;
  }
  return (
    <li>
      <span className="font-medium">{COMBINE_OP_LABELS[node.operator]}</span>
      <ul className="ml-3 border-l border-border pl-3">
        {node.inputs.map((child, index) => (
          <SketchTree key={index} node={child} searches={searches} />
        ))}
      </ul>
    </li>
  );
}

export function SeparationSketch({ taskId }: { taskId: string }): ReactElement | null {
  const chat = useChatHelpers();
  const { lanes } = taskLifecycle(chat.messages, taskId, { laneOf });
  const searches = new Map<string, Search>();
  for (const [lane, progress] of lanes) {
    if (lane === null) continue;
    const search = searchSchema.safeParse(progress.toolSpecific).data;
    if (search !== undefined) searches.set(lane, search);
  }
  const tree = runSchema.safeParse(lanes.get(null)?.toolSpecific).data?.tree;
  if (tree === undefined && searches.size === 0) return null;

  return (
    <div
      data-testid="separation-sketch"
      aria-label="How the run is building the strategy"
      className="ml-5 text-[11px] text-muted-foreground opacity-70"
    >
      {tree !== undefined ? (
        <ul data-testid="separation-sketch-tree" className="space-y-0.5">
          <SketchTree node={tree} searches={searches} />
        </ul>
      ) : (
        <ul className="space-y-0.5">
          {[...searches.entries()].map(([id, search]) => (
            <li key={id} data-testid="separation-sketch-search">
              {`${titleOf(search)} - ${countsOf(search)}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
