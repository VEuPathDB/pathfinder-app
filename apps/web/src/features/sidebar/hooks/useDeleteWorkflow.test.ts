/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { createTestQueryClient } from "@/lib/query/testing";
import { useDeleteWorkflow } from "./useDeleteWorkflow";
import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { dismissConversation } from "@pathfinder/shared/generated/hooks/useDismissConversation";

vi.mock("@pathfinder/shared/generated/hooks/useDeleteStrategy", () => ({
  deleteStrategy: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@pathfinder/shared/generated/hooks/useDismissConversation", () => ({
  dismissConversation: vi.fn(() => Promise.resolve()),
}));
vi.mock("@pathfinder/shared/generated/hooks/useRestoreStrategy", () => ({
  restoreStrategy: vi.fn(() => Promise.resolve({})),
}));
const pushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

import { chatRoot } from "@/lib/routes";

const mockDelete = vi.mocked(deleteStrategy);
const mockDismiss = vi.mocked(dismissConversation);

function chat(over: Partial<ConversationResponse>): ConversationResponse {
  return {
    id: "c1",
    name: "Conv",
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function item(over: Partial<ConversationResponse>): ConversationItem {
  const c = chat(over);
  return {
    id: c.id,
    title: c.name,
    updatedAt: c.updatedAt,
    siteId: c.siteId,
    assistantId: "pathfinder",
    isDismissed: false,
    isSaved: false,
    stepCount: 0,
    experimentId: null,
    parentConversationId: null,
    parentMessageId: null,
    chat: c,
  };
}

function renderWorkflow(activeChatId: string | null = null) {
  const client = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
  return renderHook(
    () =>
      useDeleteWorkflow({
        siteId: "plasmodb",
        reportError: vi.fn(),
        activeChatId,
      }),
    { wrapper },
  );
}

afterEach(cleanup);
beforeEach(() => {
  mockDelete.mockClear();
  mockDismiss.mockClear();
  pushMock.mockClear();
});

describe("useDeleteWorkflow.confirmDelete", () => {
  it("dismisses a non-WDK conversation by default (never hard-deletes)", async () => {
    const { result } = renderWorkflow();
    act(() => result.current.setDeleteTarget(item({ id: "n1", wdkStrategyId: null })));
    await act(async () => {
      await result.current.confirmDelete({});
    });
    expect(mockDismiss.mock.calls).toEqual([["n1"]]);
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("dismisses a WDK-linked conversation by default (strategy untouched)", async () => {
    const { result } = renderWorkflow();
    act(() => result.current.setDeleteTarget(item({ id: "w1", wdkStrategyId: 555 })));
    await act(async () => {
      await result.current.confirmDelete({});
    });
    expect(mockDismiss.mock.calls).toEqual([["w1"]]);
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("hard-deletes the conversation and its WDK strategy when opted in", async () => {
    const { result } = renderWorkflow();
    act(() => result.current.setDeleteTarget(item({ id: "w1", wdkStrategyId: 555 })));
    await act(async () => {
      await result.current.confirmDelete({ deleteLinkedStrategy: true });
    });
    expect(mockDelete.mock.calls).toEqual([["w1", { deleteFromWdk: true }]]);
    expect(mockDismiss).not.toHaveBeenCalled();
  });

  it("routes to the site chat root when the open conversation is deleted", async () => {
    const { result } = renderWorkflow("n1");
    act(() => result.current.setDeleteTarget(item({ id: "n1", wdkStrategyId: null })));
    await act(async () => {
      await result.current.confirmDelete({});
    });
    expect(chatRoot("plasmodb")).toBe("/plasmodb/conversation");
    expect(pushMock.mock.calls).toEqual([[chatRoot("plasmodb")]]);
  });

  it("leaves the route alone when a background conversation is deleted", async () => {
    const { result } = renderWorkflow("other");
    act(() => result.current.setDeleteTarget(item({ id: "n1", wdkStrategyId: null })));
    await act(async () => {
      await result.current.confirmDelete({});
    });
    expect(pushMock.mock.calls).toEqual([]);
  });
});
