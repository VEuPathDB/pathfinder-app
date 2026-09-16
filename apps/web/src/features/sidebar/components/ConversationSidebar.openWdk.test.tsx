/**
 * @vitest-environment jsdom
 */
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { SiteResponse } from "@pathfinder/shared";

import { sitesOptions } from "@/lib/api/sites";
import { createSuspenseWrapper } from "@/lib/query/testing";
import { chatUrl } from "@/lib/routes";

const routerPushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPushMock }),
  usePathname: () => "/plasmodb/conversation",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/sidebar/hooks/useChatListFetching", () => ({
  useChatListFetching: () => ({
    chats: [],
    dismissedChats: [],
    isLoading: false,
    isFetched: true,
    isSyncing: false,
    invalidate: () => Promise.resolve(),
    handleManualRefresh: () => Promise.resolve(),
  }),
}));
vi.mock("@pathfinder/shared/generated/hooks/useOpenStrategy", () => ({
  openStrategy: vi.fn(() => Promise.resolve({ conversationId: "conv-9" })),
}));

import { openStrategy } from "@pathfinder/shared/generated/hooks/useOpenStrategy";
import { ConversationSidebar } from "./ConversationSidebar";

const mockOpenStrategy = vi.mocked(openStrategy);

const server = setupServer(
  http.get("http://localhost:3000/api/v1/sites/plasmodb/strategies", () =>
    HttpResponse.json([]),
  ),
);

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

function renderSidebar() {
  const { queryClient, Wrapper } = createSuspenseWrapper();
  queryClient.setQueryData(sitesOptions().queryKey, SITES);
  return render(
    <Wrapper>
      <ConversationSidebar siteId="plasmodb" />
    </Wrapper>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("opening a VEuPathDB strategy from the conversations sidebar", () => {
  it("offers the import in the sidebar's own header menu", async () => {
    renderSidebar();

    await userEvent.click(screen.getByTestId("conversations-new-assistant-button"));

    expect(await screen.findByTestId("open-wdk-strategy-menu-item")).toHaveTextContent(
      "Open a VEuPathDB strategy",
    );
  });

  it("opens a conversation on the strategy the researcher names by link", async () => {
    renderSidebar();

    await userEvent.click(screen.getByTestId("conversations-new-assistant-button"));
    await userEvent.click(await screen.findByTestId("open-wdk-strategy-menu-item"));

    const input = await screen.findByTestId("open-wdk-strategy-input");
    await userEvent.type(
      input,
      "https://plasmodb.org/plasmo/app/workspace/strategies/214626640",
    );
    await userEvent.click(screen.getByTestId("open-wdk-strategy-confirm"));

    await waitFor(() =>
      expect(mockOpenStrategy.mock.calls).toEqual([
        [{ siteId: "plasmodb", wdkStrategyId: 214626640 }],
      ]),
    );
    await waitFor(() =>
      expect(routerPushMock.mock.calls).toEqual([[chatUrl("plasmodb", "conv-9")]]),
    );
  });

  it("refuses to send an entry that names no strategy", async () => {
    renderSidebar();

    await userEvent.click(screen.getByTestId("conversations-new-assistant-button"));
    await userEvent.click(await screen.findByTestId("open-wdk-strategy-menu-item"));

    await userEvent.type(
      await screen.findByTestId("open-wdk-strategy-input"),
      "kinase sweep",
    );

    expect(screen.getByTestId("open-wdk-strategy-confirm")).toBeDisabled();
    expect(mockOpenStrategy.mock.calls).toEqual([]);
  });
});
