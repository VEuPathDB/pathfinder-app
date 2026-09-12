// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

const pushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/plasmodb/conversation/c1",
}));
vi.mock("@/lib/api/conversations", () => ({
  duplicateConversation: vi.fn(() => Promise.resolve({ id: "copy-1", name: "Copy" })),
}));

import { duplicateConversation } from "@/lib/api/conversations";
import { chatRoot, chatUrl } from "@/lib/routes";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { useConversationSidebarActions } from "./useConversationSidebarActions";

const mockDuplicate = vi.mocked(duplicateConversation);

function makeItem(): ConversationItem {
  const chat: ConversationResponse = {
    id: "c1",
    name: "Kinase strategy",
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
  };
  return {
    id: chat.id,
    title: chat.name,
    updatedAt: chat.updatedAt,
    siteId: chat.siteId,
    assistantId: "pathfinder",
    isDismissed: false,
    isSaved: false,
    stepCount: 0,
    experimentId: null,
    parentConversationId: null,
    parentMessageId: null,
    chat,
  };
}

function renderActions() {
  return renderHook(() =>
    useConversationSidebarActions({ siteId: "plasmodb", reportError: vi.fn() }),
  );
}

afterEach(cleanup);
beforeEach(() => {
  pushMock.mockClear();
  mockDuplicate.mockClear();
});

describe("useConversationSidebarActions navigation targets", () => {
  it("pushes the site chat root for a new conversation", async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.handleNewConversation();
    });

    expect(chatRoot("plasmodb")).toBe("/plasmodb/conversation");
    expect(pushMock.mock.calls).toEqual([[chatRoot("plasmodb")]]);
  });

  it("pushes the copy's conversation route after a duplicate", async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.handleDuplicate(makeItem());
    });

    expect(mockDuplicate.mock.calls).toEqual([["c1"]]);
    expect(chatUrl("plasmodb", "copy-1")).toBe("/plasmodb/conversation/copy-1");
    expect(pushMock.mock.calls).toEqual([[chatUrl("plasmodb", "copy-1")]]);
  });
});
