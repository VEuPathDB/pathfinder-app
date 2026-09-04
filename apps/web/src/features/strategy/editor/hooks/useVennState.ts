"use client";

import { useState } from "react";

interface VennState {
  operator: string;
  swappedLabels: boolean;
  setOperator: (next: string) => void;
  swap: () => void;
}

function flipDirection(op: string): string {
  if (op === "MINUS") return "RMINUS";
  if (op === "RMINUS") return "MINUS";
  if (op === "LONLY") return "RONLY";
  if (op === "RONLY") return "LONLY";
  return op;
}

/**
 * State machine for the Venn picker. Tracks the current operator and whether
 * the user has swapped A and B (which flips MINUS↔RMINUS). External operator
 * changes (props) are reconciled via render-time prevValue.
 */
export function useVennState(initialOperator: string): VennState {
  const [operator, setOperatorState] = useState<string>(initialOperator);
  const [swappedLabels, setSwappedLabels] = useState(false);

  const [prevInitial, setPrevInitial] = useState(initialOperator);
  if (initialOperator !== prevInitial) {
    setPrevInitial(initialOperator);
    setOperatorState(initialOperator);
  }

  const setOperator = (next: string) => {
    setOperatorState(next);
  };

  const swap = () => {
    setOperatorState((current) => flipDirection(current));
    setSwappedLabels((prev) => !prev);
  };

  return {
    operator,
    swappedLabels,
    setOperator,
    swap,
  };
}
