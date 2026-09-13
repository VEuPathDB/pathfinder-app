/**
 * @vitest-environment jsdom
 */
import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/plasmodb/conversation/conv-1",
}));

vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { lastSeenFor, useRightRailStore } from "@/state/useRightRailStore";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";
import { RightRail } from "./RightRail";

const EDA_MESSAGES: UIMessage[] = [
  {
    id: "m1",
    role: "assistant",
    parts: [
      { type: "data-eda.analysis-state", data: {} },
      { type: "data-eda.subset-preview", data: {} },
      { type: "data-eda.viz", data: {} },
    ],
  },
];

function makeChat(messages: UIMessage[]): ChatHelpers {
  return {
    id: "conv-1",
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

function renderRail(messages: UIMessage[]): void {
  render(
    <ChatHelpersProvider value={makeChat(messages)}>
      <RightRail conversationId="conv-1" strategy={null} siteId="plasmodb" />
    </ChatHelpersProvider>,
  );
}

beforeEach(() => {
  useRightRailStore.setState({
    openPanel: null,
    autoOpenedConversation: null,
    ledgerSeen: {},
    lastSeen: {},
  });
});

describe("RightRail eda marker", () => {
  it("marks unseen EDA activity when the thread carries eda parts", () => {
    renderRail(EDA_MESSAGES);
    expect(screen.getByLabelText("Studies has updates")).toBeInTheDocument();
    expect(screen.queryByLabelText("Progress has updates")).toBe(null);
  });

  it("carries no marker on a thread with no eda part", () => {
    renderRail([
      {
        id: "m1",
        role: "assistant",
        parts: [{ type: "data-ledger-update", data: {} }],
      },
    ]);
    expect(screen.queryByLabelText("Studies has updates")).toBe(null);
    expect(screen.getByLabelText("Progress has updates")).toBeInTheDocument();
  });

  it("clears the marker once the eda panel records what it saw", async () => {
    renderRail(EDA_MESSAGES);
    act(() => {
      useRightRailStore.getState().openPanelId("conv-1", "eda", { edaCount: 3 });
    });
    expect(lastSeenFor(useRightRailStore.getState().lastSeen, "conv-1").edaCount).toBe(
      3,
    );
    act(() => {
      useRightRailStore.getState().closePanel();
    });
    await waitFor(() => {
      expect(screen.queryByLabelText("Studies has updates")).toBe(null);
    });
    expect(screen.getByLabelText("Open Studies")).toBeInTheDocument();
  });

  it("records what the rail icon showed when the researcher opens the panel", async () => {
    renderRail(EDA_MESSAGES);
    expect(screen.getByLabelText("Studies has updates")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Open Studies"));
    expect(screen.getByTestId("rail-eda-panel")).toBeInTheDocument();
    expect(lastSeenFor(useRightRailStore.getState().lastSeen, "conv-1").edaCount).toBe(
      3,
    );

    act(() => {
      useRightRailStore.getState().closePanel();
    });
    await waitFor(() => {
      expect(screen.queryByLabelText("Studies has updates")).toBe(null);
    });
  });

  it("marks EDA again when a later turn adds a part", () => {
    useRightRailStore.setState({
      lastSeen: {
        "conv-1": {
          strategyStepCount: 0,
          ledgerCount: 0,
          scratchpadCount: 0,
          taskCount: 0,
          memoryCount: 0,
          edaCount: 3,
        },
      },
    });
    renderRail([
      ...EDA_MESSAGES,
      { id: "m2", role: "assistant", parts: [{ type: "data-eda.viz", data: {} }] },
    ]);
    expect(screen.getByLabelText("Studies has updates")).toBeInTheDocument();
  });
});
