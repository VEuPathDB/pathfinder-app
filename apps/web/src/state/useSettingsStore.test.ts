/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from "vitest";
import { resetAllPersistedSettings, useSettingsStore } from "./useSettingsStore";

beforeEach(() => {
  useSettingsStore.getState().resetToDefaults();
});

describe("state/useSettingsStore", () => {
  it("has correct defaults", () => {
    const s = useSettingsStore.getState();
    expect(s.showRawToolCalls).toBe(false);
    expect(s.showTokenUsage).toBe(true);
    expect(s.deleteFromWdk).toBe(false);
    expect(s.phaseModels).toEqual({});
    expect(s.phaseReasoning).toEqual({});
  });

  it("setShowRawToolCalls updates state", () => {
    useSettingsStore.getState().setShowRawToolCalls(true);
    expect(useSettingsStore.getState().showRawToolCalls).toBe(true);
  });

  it("setShowTokenUsage updates state", () => {
    useSettingsStore.getState().setShowTokenUsage(false);
    expect(useSettingsStore.getState().showTokenUsage).toBe(false);
  });

  it("setDeleteFromWdk updates state", () => {
    useSettingsStore.getState().setDeleteFromWdk(true);
    expect(useSettingsStore.getState().deleteFromWdk).toBe(true);
  });

  it("setPhaseModel sets and clears per-phase model id", () => {
    useSettingsStore.getState().setPhaseModel("lead", "openai:gpt-5.4");
    expect(useSettingsStore.getState().phaseModels).toEqual({
      lead: "openai:gpt-5.4",
    });
    useSettingsStore.getState().setPhaseModel("frame", "anthropic:claude-sonnet-4-6");
    expect(useSettingsStore.getState().phaseModels).toEqual({
      lead: "openai:gpt-5.4",
      frame: "anthropic:claude-sonnet-4-6",
    });
    useSettingsStore.getState().setPhaseModel("lead", null);
    expect(useSettingsStore.getState().phaseModels).toEqual({
      frame: "anthropic:claude-sonnet-4-6",
    });
  });

  it("setPhaseReasoning sets and clears per-phase reasoning effort", () => {
    useSettingsStore.getState().setPhaseReasoning("lead", "high");
    expect(useSettingsStore.getState().phaseReasoning).toEqual({ lead: "high" });
    useSettingsStore.getState().setPhaseReasoning("lead", null);
    expect(useSettingsStore.getState().phaseReasoning).toEqual({});
  });

  it("resetToDefaults clears every map", () => {
    const store = useSettingsStore;
    store.getState().setShowRawToolCalls(true);
    store.getState().setPhaseModel("lead", "openai:gpt-5");
    store.getState().setPhaseReasoning("verification", "low");
    store.getState().resetToDefaults();
    const s = store.getState();
    expect(s.showRawToolCalls).toBe(false);
    expect(s.phaseModels).toEqual({});
    expect(s.phaseReasoning).toEqual({});
  });

  it("resetAllPersistedSettings removes the stored model picks", () => {
    useSettingsStore.getState().setPhaseModel("lead", "openai:gpt-5.4");
    expect(window.localStorage.getItem("pathfinder-settings-20260625")).toContain(
      "openai:gpt-5.4",
    );

    resetAllPersistedSettings();

    expect(
      Object.keys(window.localStorage).filter((key) => key.startsWith("pathfinder-")),
    ).toEqual([]);
  });
});
