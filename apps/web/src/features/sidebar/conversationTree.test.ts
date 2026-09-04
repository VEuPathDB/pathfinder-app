import { describe, expect, it } from "vitest";

import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { toTreeRoots } from "./conversationTree";

function makeItem(
  partial: Pick<ConversationItem, "id" | "updatedAt"> &
    Partial<
      Pick<ConversationItem, "title" | "parentConversationId" | "parentMessageId">
    >,
): ConversationItem {
  const chat: ConversationResponse = {
    id: partial.id,
    name: partial.title ?? partial.id,
    siteId: "plasmodb",
    experimentId: null,
    wdkStrategyId: null,
    isSaved: false,
    stepCount: 0,
    estimatedSize: null,
    dismissedAt: null,
    createdAt: partial.updatedAt,
    updatedAt: partial.updatedAt,
    recordType: null,
    parentConversationId: partial.parentConversationId ?? null,
    parentMessageId: partial.parentMessageId ?? null,
  };
  return {
    id: partial.id,
    title: partial.title ?? partial.id,
    updatedAt: partial.updatedAt,
    siteId: "plasmodb",
    isDismissed: false,
    isSaved: false,
    stepCount: 0,
    experimentId: null,
    parentConversationId: partial.parentConversationId ?? null,
    parentMessageId: partial.parentMessageId ?? null,
    chat,
  };
}

describe("toTreeRoots", () => {
  it("returns empty list when no items", () => {
    expect(toTreeRoots([])).toEqual([]);
  });

  it("treats items with null parent as roots", () => {
    const a = makeItem({ id: "a", updatedAt: "2026-04-10T00:00:00Z" });
    const b = makeItem({ id: "b", updatedAt: "2026-04-12T00:00:00Z" });
    const roots = toTreeRoots([a, b]);
    expect(roots.map((r) => r.item.id)).toEqual(["b", "a"]);
    expect(roots[0]?.children).toHaveLength(0);
    expect(roots[1]?.children).toHaveLength(0);
  });

  it("nests children under their parent", () => {
    const a = makeItem({ id: "a", updatedAt: "2026-04-10T00:00:00Z" });
    const b = makeItem({
      id: "b",
      updatedAt: "2026-04-11T00:00:00Z",
      parentConversationId: "a",
      parentMessageId: "msg-1",
    });
    const c = makeItem({
      id: "c",
      updatedAt: "2026-04-12T00:00:00Z",
      parentConversationId: "a",
      parentMessageId: "msg-2",
    });
    const roots = toTreeRoots([a, b, c]);
    expect(roots).toHaveLength(1);
    expect(roots[0]?.item.id).toBe("a");
    const kidIds = roots[0]?.children.map((ch) => ch.item.id);
    expect(kidIds).toEqual(["c", "b"]);
  });

  it("orders roots by most-recent-leaf in subtree DESC", () => {
    // a (old) has child b (recent) → a's subtreeLatest = b.updatedAt
    // x (medium) has no children → x's subtreeLatest = x.updatedAt
    // a should rank above x because b is the newest anywhere in a's subtree.
    const a = makeItem({ id: "a", updatedAt: "2026-01-01T00:00:00Z" });
    const b = makeItem({
      id: "b",
      updatedAt: "2026-04-20T00:00:00Z",
      parentConversationId: "a",
    });
    const x = makeItem({ id: "x", updatedAt: "2026-03-01T00:00:00Z" });
    const roots = toTreeRoots([a, b, x]);
    expect(roots.map((r) => r.item.id)).toEqual(["a", "x"]);
  });

  it("orphans (parent not in list) become roots", () => {
    const orphan = makeItem({
      id: "orphan",
      updatedAt: "2026-04-10T00:00:00Z",
      parentConversationId: "ghost-id",
    });
    const roots = toTreeRoots([orphan]);
    expect(roots.map((r) => r.item.id)).toEqual(["orphan"]);
  });

  it("handles multi-level trees", () => {
    // a -> b -> c (depth 3)
    const a = makeItem({ id: "a", updatedAt: "2026-01-01T00:00:00Z" });
    const b = makeItem({
      id: "b",
      updatedAt: "2026-02-01T00:00:00Z",
      parentConversationId: "a",
    });
    const c = makeItem({
      id: "c",
      updatedAt: "2026-03-01T00:00:00Z",
      parentConversationId: "b",
    });
    const roots = toTreeRoots([a, b, c]);
    expect(roots).toHaveLength(1);
    expect(roots[0]?.item.id).toBe("a");
    expect(roots[0]?.children[0]?.item.id).toBe("b");
    expect(roots[0]?.children[0]?.children[0]?.item.id).toBe("c");
  });
});
