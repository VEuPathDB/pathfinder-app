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
import { useSettingsModalStore } from "@/state/useSettingsModalStore";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
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
    expect(screen.getByLabelText("Review has updates")).toBeInTheDocument();

    screen.getByLabelText("Open Review").click();
    expect(useRightRailStore.getState().lastSeen["conv-1"]?.reviewCount).toBe(1);

    cleanup();
    renderRail("conv-2", []);
    expect(screen.queryByLabelText("Review has updates")).toBe(null);
  });
});

describe("the rail's panel buttons", () => {
  it("offers Strategy and Review, and Study only with a study", () => {
    renderRail("conv-1", []);
    const rail = screen.getByRole("toolbar", { name: "Right rail" });
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
      within(screen.getByRole("toolbar", { name: "Right rail" }))
        .getAllByRole("button", { name: /^Open / })
        .map((b) => b.getAttribute("aria-label")),
    ).toEqual(["Open Strategy", "Open Review", "Open Study"]);
  });
});

describe("the rail panel floats over the thread only in a narrow window", () => {
  it("floats as a drawer with a backdrop that closes it, below 900px", async () => {
    setViewportWidth(744);
    useRightRailStore.setState({ openPanel: "review" });
    renderRail("conv-1", []);
    expect(screen.getByTestId("rail-panel")).toHaveClass("max-[900px]:absolute");

    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));

    expect(useRightRailStore.getState().openPanel).toBe(null);
  });

  it("stays in flow on a wide viewport", () => {
    setViewportWidth(1440);
    useRightRailStore.setState({ openPanel: "review" });
    renderRail("conv-1", []);
    const classes = screen.getByTestId("rail-panel").className.split(" ");
    expect(classes.filter((name) => name === "absolute")).toEqual([]);
    expect(screen.getByRole("button", { name: "Close panel" })).toHaveClass(
      "min-[900px]:hidden",
    );
  });
});

describe("the rail's buttons on a phone", () => {
  it("draws its panel buttons into the phone bar and hides its own strip there", async () => {
    const slot = document.createElement("div");
    document.body.appendChild(slot);
    usePhoneBarStore.setState({ slot });
    renderRail("conv-1", []);

    expect(screen.getByRole("toolbar", { name: "Right rail" })).toHaveClass(
      "max-sm:hidden",
    );
    await userEvent.click(within(slot).getByRole("button", { name: "Open Review" }));

    expect(useRightRailStore.getState().openPanel).toBe("review");
    usePhoneBarStore.setState({ slot: null });
    slot.remove();
  });
});

describe("the right rail ends with the PathFinder mark", () => {
  beforeEach(() => {
    cleanup();
  });

  it("puts the mark below the panel buttons, as the last item of the rail", () => {
    renderRail("c-mark", []);

    const rail = screen.getByLabelText("Right rail");
    const mark = screen.getByRole("img", { name: "PathFinder" });
    expect(rail.lastElementChild?.contains(mark)).toBe(true);
    expect(rail).toContainElement(
      screen.getByRole("button", { name: "Open Strategy" }),
    );
  });

  it("puts help and the settings gear together, directly above the mark", () => {
    renderRail("c-help", []);

    const help = screen.getByRole("link", { name: "Help" });
    const gear = screen.getByRole("button", { name: "Settings" });
    const mark = screen.getByRole("img", { name: "PathFinder" });
    expect(help).toHaveAttribute("href", "/help");
    expect(help.parentElement).toBe(mark.closest("[data-rail-foot]"));
    expect(help.nextElementSibling).toBe(gear);
    expect(gear.nextElementSibling?.contains(mark)).toBe(true);
  });

  it("opens Settings from the gear beside help", async () => {
    useSettingsModalStore.setState({ isOpen: false, tab: "keys" });
    renderRail("c-gear", []);

    await userEvent.click(screen.getByRole("button", { name: "Settings" }));

    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: true,
      tab: "keys",
    });
    useSettingsModalStore.setState({ isOpen: false, tab: "model" });
  });
});
