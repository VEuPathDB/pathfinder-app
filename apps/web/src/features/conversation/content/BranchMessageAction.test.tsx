/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversation/conv-1",
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (state: { message: { id: string } }) => unknown) =>
    select({ message: { id: "msg-7" } }),
}));

vi.mock("@pathfinder/shared/generated/hooks/useForkStrategy", () => ({
  forkStrategy: vi.fn(() => Promise.resolve({ id: "fork-9" })),
}));

const toastMock = vi.hoisted(() => ({
  loading: vi.fn(),
  dismiss: vi.fn(),
  error: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { APIError } from "@/lib/api/http";
import { chatUrl } from "@/lib/routes";

import { BranchMessageAction } from "./BranchMessageAction";

describe("BranchMessageAction", () => {
  it("pushes the fork's chat url built from the path's site id", async () => {
    render(<BranchMessageAction />);

    fireEvent.click(
      screen.getByRole("button", { name: /branch to a new conversation/i }),
    );

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(chatUrl("fork-9"));
    });
    expect(vi.mocked(forkStrategy)).toHaveBeenCalledWith("conv-1", {
      fromMessageId: "msg-7",
    });
  });

  it("shows a loading toast and a busy button until the branch opens", async () => {
    let finish: (value: ConversationResponse) => void = () => {};
    vi.mocked(forkStrategy).mockImplementationOnce(
      () => new Promise((resolve) => (finish = resolve)),
    );
    render(<BranchMessageAction />);
    const button = screen.getByRole("button", {
      name: /branch to a new conversation/i,
    });

    fireEvent.click(button);

    await waitFor(() => {
      expect(toastMock.loading).toHaveBeenCalledWith("Branching this conversation...", {
        id: "branch-msg-7",
      });
    });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();

    finish({
      id: "fork-10",
      name: "Kinases (branch)",
      siteId: "plasmodb",
      recordType: null,
      createdAt: "2026-11-09T12:00:00Z",
      updatedAt: "2026-11-09T12:00:00Z",
    });

    await waitFor(() => {
      expect(toastMock.dismiss).toHaveBeenCalledWith("branch-msg-7");
    });
    expect(pushMock).toHaveBeenCalledWith(chatUrl("fork-10"));
  });

  it("turns the loading toast into the refusal when the branch fails", async () => {
    vi.mocked(forkStrategy).mockRejectedValueOnce(
      new APIError("refused", {
        status: 409,
        statusText: "Conflict",
        url: "/api/v1/conversations/conv-1/fork",
        data: { detail: "This chat is still answering." },
      }),
    );
    render(<BranchMessageAction />);

    fireEvent.click(
      screen.getByRole("button", { name: /branch to a new conversation/i }),
    );

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("This chat is still answering.", {
        id: "branch-msg-7",
      });
    });
  });
});
