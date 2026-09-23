/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DEFAULT_STREAM_NAME, type SiteResponse } from "@pathfinder/shared";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { sitesOptions } from "@/lib/api/sites";
import { createSuspenseWrapper } from "@/lib/query/testing";
import { useFirstMessageStore } from "@/state/useFirstMessageStore";

const listed = vi.hoisted(() => ({ chats: [] as ConversationResponse[] }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/plasmodb/conversation/conv-1",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/sidebar/hooks/useChatListFetching", () => ({
  useChatListFetching: () => ({
    chats: listed.chats,
    dismissedChats: [],
    isLoading: false,
    isFetched: true,
    isSyncing: false,
    invalidate: () => Promise.resolve(),
    handleManualRefresh: () => Promise.resolve(),
  }),
}));

import { ConversationSidebar } from "./ConversationSidebar";

const SITES: SiteResponse[] = [
  {
    id: "plasmodb",
    name: "PlasmoDB",
    displayName: "PlasmoDB (Plasmodium)",
    baseUrl: "https://plasmodb.org/plasmo/service",
    projectId: "PlasmoDB",
    isPortal: false,
    available: true,
    unavailableReason: null,
  },
];

function row(id: string, name: string): ConversationResponse {
  return {
    id,
    name,
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-09-23T10:00:00Z",
    updatedAt: "2026-09-23T10:00:00Z",
  };
}

function sidebar() {
  return <ConversationSidebar siteId="plasmodb" />;
}

afterEach(() => {
  cleanup();
  useFirstMessageStore.setState({ byConversation: {} });
});

describe("the name a conversation row shows before its title arrives", () => {
  it("shows the first message during the turn and the title after it", () => {
    listed.chats = [row("conv-1", ""), row("conv-2", "")];
    useFirstMessageStore
      .getState()
      .rememberFirstMessage("conv-1", [
        { id: "u1", role: "user", parts: [{ type: "text", text: "find kinases" }] },
      ]);
    const { queryClient, Wrapper } = createSuspenseWrapper();
    queryClient.setQueryData(sitesOptions().queryKey, SITES);
    const { rerender } = render(<Wrapper>{sidebar()}</Wrapper>);

    const titles = () =>
      screen.getAllByTestId("conversation-item").map((item) => item.textContent);
    expect(titles()).toEqual([
      expect.stringContaining("find kinases"),
      expect.stringContaining(DEFAULT_STREAM_NAME),
    ]);

    listed.chats = [row("conv-1", "Blood-stage kinases"), row("conv-2", "")];
    rerender(<Wrapper>{sidebar()}</Wrapper>);

    expect(titles()).toEqual([
      expect.stringContaining("Blood-stage kinases"),
      expect.stringContaining(DEFAULT_STREAM_NAME),
    ]);
    expect(screen.queryByText("find kinases")).toBeNull();
  });
});
