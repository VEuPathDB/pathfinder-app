import { useState } from "react";
import type { Node } from "@xyflow/react";

interface UseGraphSelectionArgs {
  isCompact: boolean;
}

const areNodeIdsEqual = (a: string[], b: string[]) => {
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
};

export function useGraphSelection({ isCompact }: UseGraphSelectionArgs) {
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);

  const handleSelectionChange = (selectedNodes: Node[]) => {
    if (isCompact) return;
    const nextIds = selectedNodes.map((node) => node.id).sort();
    setSelectedNodeIds((prev) => {
      if (areNodeIdsEqual(prev, nextIds)) return prev;
      return nextIds;
    });
  };

  return {
    selectedNodeIds,
    setSelectedNodeIds,
    handleSelectionChange,
  };
}
