/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ConversationResponse } from "@strategist/shared";

const thread = { isRunning: false };

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (s: { thread: typeof thread }) => unknown) =>
    select({ thread }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversation",
}));

import { strategyQueryOptions, toStrategy } from "@/lib/api/strategy";
import { createTestWrapper } from "@/lib/query/testing";
import { useThreadModeStore } from "@/state/useThreadModeStore";

import { ModeSwitch } from "./ModeSwitch";

function setup() {
  const { queryClient, Wrapper } = createTestWrapper();
  const seedDetail = (id: string, detail: Partial<ConversationResponse>) => {
    queryClient.setQueryData(
      strategyQueryOptions(id).queryKey,
      toStrategy({
        id,
        name: "t",
        siteId: "plasmodb",
        recordType: null,
        createdAt: "2026-11-06T00:00:00Z",
        updatedAt: "2026-11-06T00:00:00Z",
        ...detail,
      }),
    );
  };
  return { Wrapper, seedDetail };
}

describe("ModeSwitch", () => {
  afterEach(() => {
    useThreadModeStore.setState({ modes: {} });
    thread.isRunning = false;
  });

  it("shows all three modes and marks Auto for a new thread", () => {
    const { Wrapper } = setup();
    render(<ModeSwitch conversationId="c1" />, { wrapper: Wrapper });
    expect(
      screen
        .getAllByRole("radio")
        .map((item) => [item.textContent, item.getAttribute("aria-checked")]),
    ).toEqual([
      ["Auto", "true"],
      ["Explore", "false"],
      ["Build", "false"],
    ]);
  });

  it("switches to the mode clicked", async () => {
    const user = userEvent.setup();
    const { Wrapper } = setup();
    render(<ModeSwitch conversationId="c1" />, { wrapper: Wrapper });
    await user.click(screen.getByRole("radio", { name: "Build" }));
    expect(screen.getByRole("radio", { name: "Build" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(useThreadModeStore.getState().modes["c1"]).toBe("build");
  });

  it("keeps the mode when the current one is clicked again", async () => {
    const user = userEvent.setup();
    const { Wrapper } = setup();
    useThreadModeStore.getState().setMode("c1", "explore");
    render(<ModeSwitch conversationId="c1" />, { wrapper: Wrapper });
    await user.click(screen.getByRole("radio", { name: "Explore" }));
    expect(screen.getByRole("radio", { name: "Explore" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(useThreadModeStore.getState().modes["c1"]).toBe("explore");
  });

  it("opens on the mode the thread kept", () => {
    const { Wrapper, seedDetail } = setup();
    seedDetail("c2", { mode: "explore" });
    render(<ModeSwitch conversationId="c2" />, { wrapper: Wrapper });
    expect(screen.getByRole("radio", { name: "Explore" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("says what each mode does", () => {
    const { Wrapper } = setup();
    render(<ModeSwitch conversationId="c1" />, { wrapper: Wrapper });
    expect(screen.getByRole("radio", { name: "Build" })).toHaveAttribute(
      "title",
      "Build and change strategies",
    );
  });

  it("is disabled while a turn runs", () => {
    thread.isRunning = true;
    const { Wrapper } = setup();
    render(<ModeSwitch conversationId="c1" />, { wrapper: Wrapper });
    expect(
      screen.getAllByRole("radio").every((item) => item.hasAttribute("disabled")),
    ).toBe(true);
  });
});
