/**
 * @vitest-environment jsdom
 */
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useSessionStore } from "@/state/useSessionStore";
import { useSettingsModalStore } from "@/state/useSettingsModalStore";
import { useSettingsStore } from "@/state/useSettingsStore";

import { ChatEmptyState } from "./ChatEmptyState";

function EmptyThread({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

describe("ChatEmptyState", () => {
  beforeEach(() => {
    useSessionStore.getState().setSelectedSite("plasmodb");
  });

  it("names the site by its short name in the strategy builder's sentence", () => {
    render(
      <EmptyThread>
        <ChatEmptyState assistantId="pathfinder" />
      </EmptyThread>,
    );

    expect(screen.getByTestId("chat-empty-blurb").textContent).toBe(
      "Build and refine multi-step PlasmoDB search strategies with guided " +
        "parameter selection and validation.",
    );
  });
});

describe("ChatEmptyState first-run hint", () => {
  beforeEach(() => {
    useSessionStore.getState().setSelectedSite("plasmodb");
    useSettingsStore.setState({ firstRunHintDismissed: false });
    useSettingsModalStore.setState({ isOpen: false, tab: "keys" });
  });
  afterEach(() => {
    cleanup();
    useSettingsModalStore.setState({ isOpen: false, tab: "model" });
  });

  it("opens the settings modal on the model tab from its words", async () => {
    render(
      <EmptyThread>
        <ChatEmptyState assistantId="pathfinder" />
      </EmptyThread>,
    );

    const link = screen.getByRole("button", { name: "Settings -> Model" });
    expect(link.parentElement?.textContent).toBe(
      "Running on the default provider and models. Change the models and tiers in " +
        "Settings -> Model.",
    );
    await userEvent.click(link);

    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: true,
      tab: "model",
    });
  });
});
