/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/toxodb/conversation/conv-2",
  useRouter: () => ({ push: pushMock }),
}));

const composerText = vi.hoisted(() => ({ current: "  narrow it to kinases  " }));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (
    select: (state: {
      message: {
        id: string;
        parentId: string;
        role: string;
        content: never[];
        composer: { text: string };
      };
    }) => unknown,
  ) =>
    select({
      message: {
        id: "msg-5",
        parentId: "msg-4",
        role: "user",
        content: [],
        composer: { text: composerText.current },
      },
    }),
}));

vi.mock("@pathfinder/shared/generated/hooks/useForkStrategy", () => ({
  forkStrategy: vi.fn(() => Promise.resolve({ id: "fork-4" })),
}));

import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import { APIError } from "@/lib/api/http";
import { chatUrl } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";

import { EditComposerBranchOrRevert } from "./EditComposerSend";

describe("EditComposerBranchOrRevert", () => {
  afterEach(() => {
    composerText.current = "  narrow it to kinases  ";
    useSessionStore.getState().setPendingUserSubmission(null);
  });

  it("pushes the fork's chat url built from the path's site id", async () => {
    render(<EditComposerBranchOrRevert />);

    fireEvent.click(screen.getByTestId("edit-composer-branch-or-revert"));
    fireEvent.click(screen.getByTestId("edit-branch-button"));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(chatUrl("toxodb", "fork-4"));
    });
    expect(vi.mocked(forkStrategy)).toHaveBeenCalledWith("conv-2", {
      fromMessageId: "msg-4",
    });
    expect(useSessionStore.getState().pendingUserSubmission).toEqual({
      conversationId: "fork-4",
      content: "narrow it to kinases",
    });
  });

  it("keeps the dialog open and names the refusal when the fork fails", async () => {
    vi.mocked(forkStrategy).mockRejectedValueOnce(
      new APIError("HTTP 404 Not Found", {
        status: 404,
        statusText: "Not Found",
        url: "/api/v1/conversations/conv-2/fork",
        data: {
          type: "/errors/NOT_FOUND",
          title: "Parent message not found",
          status: 404,
          code: "NOT_FOUND",
        },
      }),
    );

    render(<EditComposerBranchOrRevert />);

    fireEvent.click(screen.getByTestId("edit-composer-branch-or-revert"));
    fireEvent.click(screen.getByTestId("edit-branch-button"));

    await waitFor(() => {
      expect(screen.getByTestId("edit-dialog-error")).toHaveTextContent(
        "Parent message not found",
      );
    });
    expect(screen.getByTestId("edit-branch-button")).toBeEnabled();
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("refuses to open the dialog while the edit composer holds no text", () => {
    composerText.current = "   ";

    render(<EditComposerBranchOrRevert />);

    const trigger = screen.getByTestId("edit-composer-branch-or-revert");
    expect(trigger).toBeDisabled();
    fireEvent.click(trigger);
    expect(screen.queryByTestId("edit-branch-button")).toBeNull();
  });
});
