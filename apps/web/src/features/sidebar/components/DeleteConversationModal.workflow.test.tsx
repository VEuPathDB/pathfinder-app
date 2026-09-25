/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { dismissConversation } from "@pathfinder/shared/generated/hooks/useDismissConversation";

import { createTestQueryClient } from "@/lib/query/testing";
import { useSettingsStore } from "@/state/useSettingsStore";
import { useDeleteWorkflow } from "@/features/sidebar/hooks/useDeleteWorkflow";
import { DeleteConversationModal } from "./DeleteConversationModal";
import type { ConversationItem } from "./conversationSidebarTypes";

vi.mock("@pathfinder/shared/generated/hooks/useDeleteStrategy", () => ({
  deleteStrategy: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@pathfinder/shared/generated/hooks/useDismissConversation", () => ({
  dismissConversation: vi.fn(() => Promise.resolve()),
}));
vi.mock("@pathfinder/shared/generated/hooks/useRestoreStrategy", () => ({
  restoreStrategy: vi.fn(() => Promise.resolve({})),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const mockDelete = vi.mocked(deleteStrategy);
const mockDismiss = vi.mocked(dismissConversation);

const CHAT: ConversationResponse = {
  id: "w1",
  name: "Kinase sweep",
  siteId: "plasmodb",
  recordType: "transcript",
  wdkStrategyId: 555,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

const ITEM: ConversationItem = {
  id: CHAT.id,
  title: CHAT.name,
  updatedAt: CHAT.updatedAt,
  siteId: CHAT.siteId,
  assistantId: "pathfinder",
  isDismissed: false,
  isSaved: false,
  stepCount: 0,
  parentConversationId: null,
  parentMessageId: null,
  chat: CHAT,
};

function SidebarDelete(): ReactElement {
  const workflow = useDeleteWorkflow({
    siteId: "plasmodb",
    reportError: vi.fn(),
    activeChatId: null,
  });
  const [asked, setAsked] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setAsked(true);
          workflow.setDeleteTarget(ITEM);
        }}
      >
        Ask
      </button>
      {asked && (
        <DeleteConversationModal
          target={workflow.deleteTarget}
          isDeleting={workflow.isDeleting}
          onClose={() => workflow.setDeleteTarget(null)}
          onConfirmDelete={(opts) => void workflow.confirmDelete(opts)}
        />
      )}
    </>
  );
}

function renderSidebarDelete(): void {
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <SidebarDelete />
    </QueryClientProvider>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  useSettingsStore.getState().resetToDefaults();
  mockDelete.mockClear();
  mockDismiss.mockClear();
});

describe("sidebar delete and the Also delete on VEuPathDB setting", () => {
  it("sends deleteFromWdk when the setting is on", async () => {
    useSettingsStore.getState().setDeleteFromWdk(true);
    renderSidebarDelete();

    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() =>
      expect(mockDelete.mock.calls).toEqual([["w1", { deleteFromWdk: true }]]),
    );
    expect(mockDismiss.mock.calls).toEqual([]);
  });

  it("moves the conversation to Recently deleted when the setting is off", async () => {
    renderSidebarDelete();

    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(mockDismiss.mock.calls).toEqual([["w1"]]));
    expect(mockDelete.mock.calls).toEqual([]);
  });
});
