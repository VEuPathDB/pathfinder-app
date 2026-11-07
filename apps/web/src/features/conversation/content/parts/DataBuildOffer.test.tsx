/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BuildOfferPayload } from "@pathfinder/shared";

const state = { message: { isLast: true }, thread: { isRunning: false } };

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (select: (s: typeof state) => unknown) => select(state),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation/conv-1",
}));

import { useThreadModeStore } from "@/state/useThreadModeStore";

import { ChatHelpersProvider } from "../../runtime/chatHelpersContext";
import { DataBuildOffer } from "./DataBuildOffer";
import { chatHelpersFor, threadOf, threadPart } from "./threadFixture";

const OFFER: BuildOfferPayload = {
  label: "Proteins with exactly seven transmembrane domains",
  geneCount: 412,
};

function offered(sendMessage = vi.fn(async () => {})) {
  const helpers = {
    ...chatHelpersFor(threadOf([threadPart("data-build-offer", OFFER)])),
    sendMessage,
  };
  render(
    <ChatHelpersProvider value={helpers}>
      <DataBuildOffer data={OFFER} />
    </ChatHelpersProvider>,
  );
  return sendMessage;
}

describe("DataBuildOffer", () => {
  afterEach(() => {
    useThreadModeStore.setState({ modes: {} });
    state.message.isLast = true;
    state.thread.isRunning = false;
  });

  it("offers to build the one counted reading with its count", () => {
    offered();

    expect(screen.getByRole("button", { name: "Build it" })).toBeInTheDocument();
    expect(screen.getByTestId("build-offer")).toHaveTextContent(
      "Proteins with exactly seven transmembrane domains (412 genes)",
    );
  });

  it("switches the thread to Build and sends the reading", async () => {
    const user = userEvent.setup();
    useThreadModeStore.getState().setMode("conv-1", "explore");
    const sendMessage = offered();

    await user.click(screen.getByRole("button", { name: "Build it" }));

    expect(useThreadModeStore.getState().modes["conv-1"]).toBe("build");
    expect(sendMessage).toHaveBeenCalledWith({
      text: 'Build "Proteins with exactly seven transmembrane domains".',
    });
  });

  it("shows nothing under an earlier reply", () => {
    state.message.isLast = false;
    offered();

    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("is disabled while a turn runs", () => {
    state.thread.isRunning = true;
    offered();

    expect(screen.getByRole("button", { name: "Build it" })).toBeDisabled();
  });
});
