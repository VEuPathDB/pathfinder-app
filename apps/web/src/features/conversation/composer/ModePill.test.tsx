/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ConversationResponse } from "@pathfinder/shared";

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

import { ModePill } from "./ModePill";

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

describe("ModePill", () => {
  afterEach(() => {
    useThreadModeStore.setState({ modes: {} });
    thread.isRunning = false;
  });

  it("starts on Auto for a new thread", () => {
    const { Wrapper } = setup();
    render(<ModePill conversationId="c1" />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: "Mode: Auto" })).toBeInTheDocument();
  });

  it("cycles Auto, Explore, Build and back to Auto", async () => {
    const user = userEvent.setup();
    const { Wrapper } = setup();
    render(<ModePill conversationId="c1" />, { wrapper: Wrapper });
    await user.click(screen.getByRole("button", { name: "Mode: Auto" }));
    expect(screen.getByRole("button", { name: "Mode: Explore" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mode: Explore" }));
    expect(screen.getByRole("button", { name: "Mode: Build" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mode: Build" }));
    expect(screen.getByRole("button", { name: "Mode: Auto" })).toBeInTheDocument();
  });

  it("opens on the mode the thread kept", () => {
    const { Wrapper, seedDetail } = setup();
    seedDetail("c2", { mode: "explore" });
    render(<ModePill conversationId="c2" />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: "Mode: Explore" })).toBeInTheDocument();
  });

  it("says what the current mode does", () => {
    const { Wrapper } = setup();
    useThreadModeStore.getState().setMode("c1", "build");
    render(<ModePill conversationId="c1" />, { wrapper: Wrapper });
    expect(screen.getByTestId("mode-pill")).toHaveAttribute(
      "title",
      "Build and change strategies",
    );
  });

  it("is disabled while a turn runs", () => {
    thread.isRunning = true;
    const { Wrapper } = setup();
    render(<ModePill conversationId="c1" />, { wrapper: Wrapper });
    expect(screen.getByTestId("mode-pill")).toBeDisabled();
  });
});
