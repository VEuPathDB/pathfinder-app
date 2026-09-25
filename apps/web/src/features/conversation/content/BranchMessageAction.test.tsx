/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation/conv-1",
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (state: { message: { id: string } }) => unknown) =>
    select({ message: { id: "msg-7" } }),
}));

vi.mock("@pathfinder/shared/generated/hooks/useForkStrategy", () => ({
  forkStrategy: vi.fn(() => Promise.resolve({ id: "fork-9" })),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import { chatUrl } from "@/lib/routes";

import { BranchMessageAction } from "./BranchMessageAction";

describe("BranchMessageAction", () => {
  it("pushes the fork's chat url built from the path's site id", async () => {
    render(<BranchMessageAction />);

    fireEvent.click(
      screen.getByRole("button", { name: /branch to a new conversation/i }),
    );

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(chatUrl("plasmodb", "fork-9"));
    });
    expect(vi.mocked(forkStrategy)).toHaveBeenCalledWith("conv-1", {
      fromMessageId: "msg-7",
    });
  });
});
