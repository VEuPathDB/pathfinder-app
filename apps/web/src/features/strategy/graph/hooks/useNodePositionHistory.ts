import { useRef } from "react";
import type { Node } from "@xyflow/react";
import type { Step } from "@pathfinder/shared";

type NodeData = {
  step?: Step;
  message?: string;
};

function buildNodePositionKey(list: Node[]): string {
  return list
    .map(
      (node) =>
        `${node.id}:${Math.round(node.position.x * 100) / 100}:${
          Math.round(node.position.y * 100) / 100
        }`,
    )
    .sort()
    .join("|");
}

function cloneNodes(list: Node[]): Node[] {
  return list.map((node) => {
    const cloned: Node = {
      ...node,
      position: { ...node.position },
      data: { ...(node.data as NodeData) },
    };
    return cloned;
  });
}

export function useNodePositionHistory(args: {
  setNodes: (updater: Node[] | ((prev: Node[]) => Node[])) => void;
  maxSnapshots?: number;
}) {
  const { setNodes, maxSnapshots = 50 } = args;

  const historyRef = useRef<Node[][]>([]);
  const historyIndexRef = useRef(-1);
  const historyKeyRef = useRef<string | null>(null);

  const pushSnapshot = (nodes: Node[]) => {
    if (nodes.length === 0) return;
    const nextKey = buildNodePositionKey(nodes);
    if (nextKey === historyKeyRef.current) return;

    const snapshot = cloneNodes(nodes);
    const history = historyRef.current.slice(0, historyIndexRef.current + 1);
    history.push(snapshot);
    if (history.length > maxSnapshots) history.shift();

    historyRef.current = history;
    historyIndexRef.current = history.length - 1;
    historyKeyRef.current = nextKey;
  };

  const reset = (nodes: Node[]) => {
    historyRef.current = [];
    historyIndexRef.current = -1;
    historyKeyRef.current = null;
    pushSnapshot(nodes);
  };

  const tryUndo = (): boolean => {
    if (historyIndexRef.current <= 0) return false;
    historyIndexRef.current -= 1;
    const snapshot = historyRef.current[historyIndexRef.current];
    if (!snapshot) return false;
    historyKeyRef.current = buildNodePositionKey(snapshot);
    setNodes(cloneNodes(snapshot));
    return true;
  };

  const tryRedo = (): boolean => {
    const history = historyRef.current;
    if (historyIndexRef.current >= history.length - 1) return false;
    historyIndexRef.current += 1;
    const snapshot = history[historyIndexRef.current];
    if (!snapshot) return false;
    historyKeyRef.current = buildNodePositionKey(snapshot);
    setNodes(cloneNodes(snapshot));
    return true;
  };

  return {
    pushSnapshot,
    reset,
    tryUndo,
    tryRedo,
  };
}
