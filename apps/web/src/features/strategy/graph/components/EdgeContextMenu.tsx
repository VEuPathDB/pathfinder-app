"use client";

import type { Edge } from "@xyflow/react";
import { Trash2 } from "lucide-react";
import { combineOpEnum, type CombineOp, type Step } from "@pathfinder/shared";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { VennIcon } from "@/features/strategy/graph/components/VennIcon";
import { inferStepKind } from "@/features/strategy/graph";
import { cn } from "@/lib/utils/cn";

const OPERATOR_GRID: readonly CombineOp[] = [
  combineOpEnum.UNION,
  combineOpEnum.INTERSECT,
  combineOpEnum.MINUS,
  combineOpEnum.RMINUS,
];

const OPERATOR_LABEL: Record<string, string> = {
  [combineOpEnum.UNION]: "Union",
  [combineOpEnum.INTERSECT]: "Intersect",
  [combineOpEnum.MINUS]: "A only",
  [combineOpEnum.RMINUS]: "B only",
};

interface EdgeContextMenuProps {
  edge: Edge;
  x: number;
  y: number;
  steps: Step[];
  onDeleteEdge: (edge: Edge) => void;
  onChangeOperator: (stepId: string, operator: CombineOp) => void;
  onClose: () => void;
}

/**
 * Programmatic edge action menu — anchored at the click coordinates via a
 * virtual `PopoverAnchor`. Combine edges expose an operator picker; other
 * edges just expose Delete.
 *
 * Why Popover and not shadcn `ContextMenu`?
 *
 * Radix `ContextMenu.Trigger` is a `Primitive.span` that owns the
 * `contextmenu` listener and tracks the pointer via an internal virtual
 * ref. It REQUIRES a persistent DOM element to attach to. ReactFlow renders
 * each edge as an SVG `<path>` inside a per-edge `<svg><g>` wrapper, and
 * Radix's HTML `<span>` trigger cannot be a child of `<svg>`. Wrapping the
 * whole canvas in one `ContextMenu.Trigger` would hijack right-click for
 * nodes, panels, and the pane (conflicting with ReactFlow's own
 * `onPaneContextMenu` / `onNodeContextMenu` / `onSelectionContextMenu`)
 * and would still need a virtual-anchor escape hatch like this one.
 *
 * `Popover` + `PopoverAnchor asChild` lets us anchor the floating UI at
 * arbitrary `(x, y)` coordinates produced by ReactFlow's edge-event handler
 * without owning the trigger DOM, which is the right primitive for "menu
 * positioned at the mouse, opened by upstream code."
 */
export function EdgeContextMenu({
  edge,
  x,
  y,
  steps,
  onDeleteEdge,
  onChangeOperator,
  onClose,
}: EdgeContextMenuProps) {
  const targetStep = steps.find((s) => s.id === edge.target);
  const isCombineEdge = targetStep != null && inferStepKind(targetStep) === "combine";

  return (
    <Popover
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <PopoverAnchor asChild>
        <span
          aria-hidden
          style={{
            position: "fixed",
            left: x,
            top: y,
            width: 0,
            height: 0,
            pointerEvents: "none",
          }}
        />
      </PopoverAnchor>
      <PopoverContent
        align="start"
        side="bottom"
        className="w-auto min-w-[200px] p-1"
        role="menu"
        aria-label="Edge actions"
      >
        {isCombineEdge && (
          <>
            <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Change operator
            </div>
            <div
              className="grid grid-cols-2 gap-1 p-1"
              data-testid="edge-context-menu-operator-grid"
            >
              {OPERATOR_GRID.map((op) => {
                const active = targetStep.operator === op;
                return (
                  <button
                    key={op}
                    type="button"
                    role="menuitemradio"
                    onClick={() => {
                      onChangeOperator(edge.target, op);
                    }}
                    aria-checked={active}
                    aria-label={`Set operator to ${OPERATOR_LABEL[op] ?? op}`}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors",
                      active
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border text-muted-foreground hover:border-input hover:bg-accent hover:text-foreground",
                    )}
                  >
                    <span className="mr-1.5">
                      <VennIcon operator={op} />
                    </span>
                    <span>{OPERATOR_LABEL[op] ?? op}</span>
                  </button>
                );
              })}
            </div>
            <div className="my-1 h-px bg-border" />
          </>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full justify-start text-destructive hover:bg-destructive/5 hover:text-destructive"
          onClick={() => onDeleteEdge(edge)}
          role="menuitem"
        >
          <Trash2 className="size-4" />
          Delete edge
        </Button>
      </PopoverContent>
    </Popover>
  );
}
