/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/conversation/conv-1",
}));

import { usePhoneBarStore } from "@/state/usePhoneBarStore";
import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { RailToggle } from "./RailToggle";
import { RightRail } from "./RightRail";

function makeChat(messages: UIMessage[], id: string): ChatHelpers {
  return {
    id,
    messages,
    status: "ready",
    error: undefined,
    setMessages: () => {},
    sendMessage: async () => {},
    regenerate: async () => {},
    stop: async () => {},
    addToolResult: async () => {},
    addToolOutput: async () => {},
    addToolApprovalResponse: () => {},
    clearError: () => {},
  };
}

function renderRail(conversationId: string, messages: UIMessage[]): void {
  render(
    <ChatHelpersProvider value={makeChat(messages, conversationId)}>
      <RailToggle conversationId={conversationId} strategy={null} />
      <RightRail conversationId={conversationId} strategy={null} siteId="plasmodb" />
    </ChatHelpersProvider>,
  );
}

function setViewportWidth(width: number): void {
  window.innerWidth = width;
  window.innerHeight = 900;
}

const TASK_STARTED: UIMessage[] = [
  {
    id: "m1",
    role: "assistant",
    parts: [{ type: "data-background-task-started", data: {} }],
  },
];

beforeEach(() => {
  useRightRailStore.setState({
    openPanel: null,
    autoOpenedConversation: null,
    lastSeen: {},
  });
  useLeftSidebarStore.setState({ collapsed: false });
  setViewportWidth(1440);
});

describe("the rail badge is scoped to the open conversation", () => {
  it("raises no Review dot on a fresh conversation after another one ran a task", () => {
    renderRail("conv-1", TASK_STARTED);
    expect(
      screen.getByRole("button", { name: "Open Review" }),
    ).toHaveAccessibleDescription("Review has updates");

    screen.getByLabelText("Open Review").click();
    expect(useRightRailStore.getState().lastSeen["conv-1"]?.reviewCount).toBe(1);

    cleanup();
    renderRail("conv-2", []);
    expect(screen.queryByText("Review has updates")).toBe(null);
  });
});

describe("the rail's panel buttons", () => {
  it("offers Strategy and Review, and Study only with a study", () => {
    renderRail("conv-1", []);
    const rail = screen.getByRole("toolbar", { name: "Side panels" });
    expect(
      within(rail)
        .getAllByRole("button", { name: /^Open / })
        .map((b) => b.getAttribute("aria-label")),
    ).toEqual(["Open Strategy", "Open Review"]);

    cleanup();
    renderRail("conv-2", [
      { id: "m1", role: "assistant", parts: [{ type: "data-eda.viz", data: {} }] },
    ]);
    expect(
      within(screen.getByRole("toolbar", { name: "Side panels" }))
        .getAllByRole("button", { name: /^Open / })
        .map((b) => b.getAttribute("aria-label")),
    ).toEqual(["Open Strategy", "Open Review", "Open Study"]);
  });
});

describe("the rail panel floats over the thread when the chat would drop below 600px", () => {
  it("floats as a drawer with a backdrop that closes it", async () => {
    setViewportWidth(980);
    useLeftSidebarStore.setState({ collapsed: true });
    useRightRailStore.setState({ openPanel: "review" });
    renderRail("conv-1", []);
    expect(screen.getByTestId("rail-panel")).toHaveClass("absolute");

    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));

    expect(useRightRailStore.getState().openPanel).toBe(null);
  });

  it("stays beside the chat when the chat keeps 600px", () => {
    setViewportWidth(1440);
    useLeftSidebarStore.setState({ collapsed: true });
    useRightRailStore.setState({ openPanel: "review" });
    renderRail("conv-1", []);
    expect(screen.getByTestId("rail-panel").className.split(" ")).not.toContain(
      "absolute",
    );
    expect(screen.queryByRole("button", { name: "Close panel" })).toBe(null);
  });
});

describe("the rail's buttons on a phone", () => {
  it("draws its panel buttons into the phone bar and hides its own strip there", async () => {
    const slot = document.createElement("div");
    document.body.appendChild(slot);
    usePhoneBarStore.setState({ slot });
    renderRail("conv-1", []);

    expect(
      screen.getByRole("toolbar", { name: "Side panels" }).parentElement,
    ).toHaveClass("max-sm:hidden");
    await userEvent.click(within(slot).getByRole("button", { name: "Open Review" }));

    expect(useRightRailStore.getState().openPanel).toBe("review");
    usePhoneBarStore.setState({ slot: null });
    slot.remove();
  });
});
