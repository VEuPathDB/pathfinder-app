/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";

import { DeleteConversationModal } from "./DeleteConversationModal";
import type { ConversationItem } from "./conversationSidebarTypes";

function makeItem(over: Partial<ConversationResponse> = {}): ConversationItem {
  const chat: ConversationResponse = {
    id: "c1",
    name: "Kinase sweep",
    siteId: "plasmodb",
    recordType: "transcript",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
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

afterEach(cleanup);

describe("DeleteConversationModal", () => {
  it("defaults to dismiss (deleteLinkedStrategy false) on confirm", async () => {
    const onConfirmDelete = vi.fn();
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: 555 })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={onConfirmDelete}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(onConfirmDelete.mock.calls).toEqual([[{ deleteLinkedStrategy: false }]]);
  });

  it("offers 'Also delete strategy from PlasmoDB' for a WDK-linked chat and reports it when checked", async () => {
    const onConfirmDelete = vi.fn();
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: 555 })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={onConfirmDelete}
      />,
    );
    const checkbox = screen.getByRole("checkbox", {
      name: /also delete strategy from plasmodb/i,
    });
    await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(onConfirmDelete.mock.calls).toEqual([[{ deleteLinkedStrategy: true }]]);
  });

  it("hides the strategy checkbox for a chat with no WDK strategy", () => {
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: null })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={vi.fn()}
      />,
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeEnabled();
  });

  it("tells the user the delete is recoverable", () => {
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: null })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/can be restored|recently deleted/i)).toBeVisible();
  });

  it("names a strategy PathFinder created", () => {
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: 555, wdkStrategyCreatedHere: true })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={vi.fn()}
      />,
    );

    expect(screen.getByTestId("delete-linked-strategy-note")).toHaveTextContent(
      "PathFinder created this strategy in PlasmoDB (Plasmodium). Deleting it is permanent, and the conversation will not be recoverable.",
    );
  });

  it("says only what the record supports when PathFinder did not claim the strategy", () => {
    render(
      <DeleteConversationModal
        target={makeItem({ wdkStrategyId: 555, wdkStrategyCreatedHere: false })}
        isDeleting={false}
        onClose={vi.fn()}
        onConfirmDelete={vi.fn()}
      />,
    );

    expect(screen.getByTestId("delete-linked-strategy-note")).toHaveTextContent(
      "PathFinder has no record of creating this strategy in PlasmoDB (Plasmodium), so it may be one you made there yourself. Deleting it is permanent, and the conversation will not be recoverable.",
    );
  });
});
