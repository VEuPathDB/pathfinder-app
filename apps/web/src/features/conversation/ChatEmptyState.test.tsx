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
import suggestedQuestions from "./data/suggestedQuestions.json";

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

  it("offers at least one suggestion on every site of the bank", () => {
    const empty = Object.entries(suggestedQuestions)
      .filter(([, prompts]) => prompts.length === 0)
      .map(([siteId]) => siteId);

    expect(empty).toEqual([]);
  });

  it("offers every suggestion of the selected site", () => {
    useSessionStore.getState().setSelectedSite("orthomcl");
    render(
      <EmptyThread>
        <ChatEmptyState assistantId="pathfinder" />
      </EmptyThread>,
    );

    for (const prompt of suggestedQuestions.orthomcl) {
      expect(screen.getByRole("button", { name: prompt })).toBeInTheDocument();
    }
    expect(suggestedQuestions.orthomcl).toContain(
      "List ortholog groups with exactly one protein from every apicomplexan genome.",
    );
  });
});

describe("ChatEmptyState first-run hint", () => {
  beforeEach(() => {
    useSessionStore.getState().setSelectedSite("plasmodb");
    useSettingsStore.getState().resetToDefaults();
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

  function drawHint(): void {
    render(
      <EmptyThread>
        <ChatEmptyState assistantId="pathfinder" />
      </EmptyThread>,
    );
  }

  it("shows the notice while the model settings are the defaults", () => {
    drawHint();

    expect(
      screen.getByRole("button", { name: "Settings -> Model" }),
    ).toBeInTheDocument();
  });

  it("hides the notice once a role runs on a model of its own", () => {
    useSettingsStore.getState().setPhaseModel("lead", "openai:gpt-5.6-mini");
    drawHint();

    expect(screen.queryAllByRole("button", { name: "Settings -> Model" })).toHaveLength(
      0,
    );
  });

  it("hides the notice once a role runs at an effort of its own", () => {
    useSettingsStore.getState().setPhaseReasoning("lead", "high");
    drawHint();

    expect(screen.queryAllByRole("button", { name: "Settings -> Model" })).toHaveLength(
      0,
    );
  });

  it("hides the notice once a tier or a provider is picked", () => {
    useSettingsStore
      .getState()
      .applyPhasePreset({ lead: "anthropic:claude-sonnet-5-5" }, { lead: "medium" });
    drawHint();

    expect(screen.queryAllByRole("button", { name: "Settings -> Model" })).toHaveLength(
      0,
    );
  });

  it("hides the notice once it is dismissed", async () => {
    drawHint();

    await userEvent.click(screen.getByRole("button", { name: "Dismiss hint" }));

    expect(screen.queryAllByRole("button", { name: "Settings -> Model" })).toHaveLength(
      0,
    );
    expect(useSettingsStore.getState().firstRunHintDismissed).toBe(true);
  });
});
