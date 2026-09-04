"use client";

import { useState } from "react";
import { ArrowRightLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";
import {
  setIntersect,
  setUnion,
  setDifference,
} from "@/features/workbench/utils/setOperations";
import type { GeneSet } from "@pathfinder/shared";

type Operation = "intersect" | "union" | "minus";

const OPS: { key: Operation; symbol: string; label: string }[] = [
  { key: "intersect", symbol: "\u2229", label: "Intersect" },
  { key: "union", symbol: "\u222A", label: "Union" },
  { key: "minus", symbol: "\u2212", label: "Minus" },
];

interface ComposeBarProps {
  setA: GeneSet;
  setB: GeneSet;
  onExecute: (result: {
    operation: Operation;
    geneIds: string[];
    name: string;
  }) => void;
  loading?: boolean;
}

export function ComposeBar({ setA, setB, onExecute, loading }: ComposeBarProps) {
  const [operation, setOperation] = useState<Operation>("intersect");
  const [swapped, setSwapped] = useState(false);

  const left = swapped ? setB : setA;
  const right = swapped ? setA : setB;

  const result = (() => {
    switch (operation) {
      case "intersect":
        return setIntersect(left.geneIds, right.geneIds);
      case "union":
        return setUnion(left.geneIds, right.geneIds);
      case "minus":
        return setDifference(left.geneIds, right.geneIds);
    }
  })();

  const opSymbol = OPS.find((o) => o.key === operation)!.symbol;
  const resultName = `${left.name} ${opSymbol} ${right.name}`;

  const handleExecute = () => {
    onExecute({ operation, geneIds: result, name: resultName });
  };

  return (
    <div className="space-y-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Compose
      </p>

      {/* Operands row */}
      <div className="flex items-center gap-1.5">
        <div
          className="min-w-0 flex-1 truncate rounded-md bg-muted px-2 py-1 text-xs font-medium"
          title={left.name}
        >
          {left.name}
        </div>

        <button
          type="button"
          onClick={() => setSwapped((s) => !s)}
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Swap operands"
        >
          <ArrowRightLeft className="h-3.5 w-3.5" />
        </button>

        <div
          className="min-w-0 flex-1 truncate rounded-md bg-muted px-2 py-1 text-xs font-medium"
          title={right.name}
        >
          {right.name}
        </div>
      </div>

      {/* Operation picker */}
      <div className="flex rounded-lg bg-muted p-0.5">
        {OPS.map((op) => (
          <button
            key={op.key}
            type="button"
            onClick={() => setOperation(op.key)}
            aria-label={op.label}
            className={cn(
              "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors duration-150",
              operation === op.key
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="text-sm font-semibold">{op.symbol}</span>
            {op.label}
          </button>
        ))}
      </div>

      {/* Result preview + create */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground tabular-nums">
            {result.length.toLocaleString()}
          </span>{" "}
          gene{result.length !== 1 ? "s" : ""}
        </p>
        <Button
          size="sm"
          onClick={handleExecute}
          loading={loading === true}
          disabled={result.length === 0}
          className="gap-1 text-xs"
        >
          <Plus className="h-3 w-3" />
          Create
        </Button>
      </div>
    </div>
  );
}
