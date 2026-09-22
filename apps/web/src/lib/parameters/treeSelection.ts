import type { VocabNode } from "@/lib/utils/vocab";

/** The check state of one tree node and the leaves beneath it. */
type NodeState = {
  checked: boolean | "indeterminate";
  leaves: string[];
};

/** One item of the smallest set of labels that names a selection. */
type SelectionSummary = {
  value: string;
  label: string;
  kind: "branch" | "leaf";
  leafCount: number;
};

function isBranch(node: VocabNode): node is VocabNode & { children: VocabNode[] } {
  return node.children != null && node.children.length > 0;
}

function collectLeaves(node: VocabNode): string[] {
  return isBranch(node) ? node.children.flatMap(collectLeaves) : [node.value];
}

function indexNodes(tree: VocabNode[]): Map<string, VocabNode> {
  const byValue = new Map<string, VocabNode>();
  const visit = (node: VocabNode): void => {
    byValue.set(node.value, node);
    node.children?.forEach(visit);
  };
  tree.forEach(visit);
  return byValue;
}

function checkedOf(
  leaves: string[],
  selected: ReadonlySet<string>,
): NodeState["checked"] {
  const count = leaves.filter((leaf) => selected.has(leaf)).length;
  if (count === 0) return false;
  return count === leaves.length ? true : "indeterminate";
}

/**
 * The state of every node, keyed by value, in one post-order pass. A branch is
 * checked when every leaf is selected, indeterminate when some are.
 */
export function nodeStates(
  tree: VocabNode[],
  selected: ReadonlySet<string>,
): Map<string, NodeState> {
  const states = new Map<string, NodeState>();
  const visit = (node: VocabNode): string[] => {
    const leaves = isBranch(node) ? node.children.flatMap(visit) : [node.value];
    states.set(node.value, { checked: checkedOf(leaves, selected), leaves });
    return leaves;
  };
  tree.forEach(visit);
  return states;
}

/** Replace each branch term by the leaves beneath it; keep terms the tree lacks. */
export function toLeaves(values: string[], tree: VocabNode[]): string[] {
  const byValue = indexNodes(tree);
  const out = new Set<string>();
  for (const value of values) {
    const node = byValue.get(value);
    const leaves = node === undefined ? [value] : collectLeaves(node);
    for (const leaf of leaves) out.add(leaf);
  }
  return [...out];
}

/** Every branch on the path from a root to a selected leaf. */
export function ancestorsOfSelected(
  tree: VocabNode[],
  selectedLeaves: string[],
): Set<string> {
  const selected = new Set(selectedLeaves);
  const out = new Set<string>();
  const visit = (node: VocabNode): boolean => {
    if (!isBranch(node)) return selected.has(node.value);
    const holds = node.children.map(visit).some(Boolean);
    if (holds) out.add(node.value);
    return holds;
  };
  tree.forEach(visit);
  return out;
}

/** The vocabulary term PathFinder shows as the "All" root. */
const ALL_TERM = "@@fake@@";

/**
 * The branches shown open when the user has toggled nothing. Multi-pick opens
 * each partly selected branch; single-pick opens the path to the pick.
 */
export function derivedExpansion(
  tree: VocabNode[],
  states: Map<string, NodeState>,
  selectedLeaves: string[],
  { multiPick }: { multiPick: boolean },
): Set<string> {
  const expanded = multiPick
    ? partialBranches(states)
    : ancestorsOfSelected(tree, selectedLeaves);
  const nothingSelected = tree.every(
    (node) => states.get(node.value)?.checked === false,
  );
  const only = tree.length === 1 ? tree[0] : undefined;
  if (nothingSelected && only !== undefined && isBranch(only)) {
    expanded.add(only.value);
    const lone = only.children.length === 1 ? only.children[0] : undefined;
    if (only.value === ALL_TERM && lone !== undefined && isBranch(lone)) {
      expanded.add(lone.value);
    }
  }
  return expanded;
}

function partialBranches(states: Map<string, NodeState>): Set<string> {
  const out = new Set<string>();
  for (const [value, state] of states) {
    if (state.checked === "indeterminate") out.add(value);
  }
  return out;
}

/**
 * The top-most fully selected branches plus the selected leaves outside them,
 * in tree pre-order. Terms the tree lacks follow as leaves named by value.
 */
export function summarizeSelection(
  tree: VocabNode[],
  states: Map<string, NodeState>,
  selectedLeaves: string[],
): SelectionSummary[] {
  const out: SelectionSummary[] = [];
  const visit = (node: VocabNode): void => {
    const state = states.get(node.value);
    if (state === undefined || state.checked === false) return;
    if (state.checked === true) {
      out.push({
        value: node.value,
        label: node.label,
        kind: isBranch(node) ? "branch" : "leaf",
        leafCount: state.leaves.length,
      });
      return;
    }
    node.children?.forEach(visit);
  };
  tree.forEach(visit);
  const known = indexNodes(tree);
  for (const leaf of selectedLeaves) {
    if (!known.has(leaf))
      out.push({ value: leaf, label: leaf, kind: "leaf", leafCount: 1 });
  }
  return out;
}

/** A summary item as a researcher reads it: "B (all 2)" or the leaf label. */
export function summaryLabel(item: SelectionSummary): string {
  return item.kind === "branch"
    ? `${item.label} (all ${String(item.leafCount)})`
    : item.label;
}
