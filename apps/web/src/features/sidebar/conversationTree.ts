import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";

/**
 * Conversation-fork tree node. ``subtreeLatest`` is the max ``updatedAt``
 * across the whole subtree — used to sort roots/children by freshness so the
 * most-recently-active threads bubble up even when their root is old.
 */
export interface TreeNode {
  item: ConversationItem;
  children: TreeNode[];
  subtreeLatest: number;
}

/** Build roots + children from a flat list, sorted by most-recent leaf DESC. */
export function toTreeRoots(items: readonly ConversationItem[]): TreeNode[] {
  const ids = new Set(items.map((i) => i.id));
  const nodes = new Map<string, TreeNode>();
  for (const it of items) {
    nodes.set(it.id, {
      item: it,
      children: [],
      subtreeLatest: Date.parse(it.updatedAt),
    });
  }
  const roots: TreeNode[] = [];
  for (const it of items) {
    const self = nodes.get(it.id);
    if (!self) continue;
    const parentId = it.parentConversationId;
    if (parentId != null && ids.has(parentId)) {
      nodes.get(parentId)?.children.push(self);
    } else {
      roots.push(self);
    }
  }
  const computeLatest = (node: TreeNode): number => {
    let latest = Date.parse(node.item.updatedAt);
    for (const child of node.children) {
      const childLatest = computeLatest(child);
      if (childLatest > latest) latest = childLatest;
    }
    node.subtreeLatest = latest;
    node.children.sort((a, b) => b.subtreeLatest - a.subtreeLatest);
    return latest;
  };
  for (const r of roots) computeLatest(r);
  roots.sort((a, b) => b.subtreeLatest - a.subtreeLatest);
  return roots;
}
