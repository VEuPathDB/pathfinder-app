// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { chatUrl } from "@/lib/routes";
import { ConversationSubtree, type SubtreeNode } from "./ConversationSubtree";
import type { ConversationItem } from "./conversationSidebarTypes";

function makeItem(id: string, siteId: string): ConversationItem {
  const chat: ConversationResponse = {
    id,
    name: `Branch ${id}`,
    siteId,
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
  };
  return {
    id,
    title: chat.name,
    updatedAt: chat.updatedAt,
    siteId,
    assistantId: "pathfinder",
    isDismissed: false,
    isSaved: false,
    stepCount: 0,
    parentConversationId: null,
    parentMessageId: null,
    chat,
  };
}

const nodes: SubtreeNode[] = [
  {
    item: makeItem("b1", "plasmodb"),
    children: [{ item: makeItem("b2", "toxodb"), children: [] }],
  },
];

describe("ConversationSubtree branch links", () => {
  afterEach(cleanup);

  it("points every visible branch at its own site-scoped conversation route", () => {
    render(
      <ConversationSubtree
        rootId="root-1"
        nodes={nodes}
        activeId={null}
        onStartDelete={vi.fn()}
      />,
    );

    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([chatUrl("plasmodb", "b1"), chatUrl("toxodb", "b2")]);
    expect(hrefs).toEqual(["/plasmodb/conversation/b1", "/toxodb/conversation/b2"]);
  });
});
