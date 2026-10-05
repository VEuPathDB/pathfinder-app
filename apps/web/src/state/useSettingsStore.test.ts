/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from "vitest";
import { resetAllPersistedSettings, useSettingsStore } from "./useSettingsStore";
import {
  ANTHROPIC_SMALL,
  OPENAI_FLAGSHIP,
  OPENAI_SMALL,
} from "@/lib/models/__fixtures__/models";

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
    useSettingsStore.getState().setPhaseModel("lead", OPENAI_FLAGSHIP.id);
    expect(useSettingsStore.getState().phaseModels).toEqual({
      lead: OPENAI_FLAGSHIP.id,
    });
    useSettingsStore.getState().setPhaseModel("frame", ANTHROPIC_SMALL.id);
    expect(useSettingsStore.getState().phaseModels).toEqual({
      lead: OPENAI_FLAGSHIP.id,
      frame: ANTHROPIC_SMALL.id,
    });
    useSettingsStore.getState().setPhaseModel("lead", null);
    expect(useSettingsStore.getState().phaseModels).toEqual({
      frame: ANTHROPIC_SMALL.id,
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
    store.getState().setPhaseModel("lead", OPENAI_SMALL.id);
    store.getState().setPhaseReasoning("verification", "low");
    store.getState().resetToDefaults();
    const s = store.getState();
    expect(s.showRawToolCalls).toBe(false);
    expect(s.phaseModels).toEqual({});
    expect(s.phaseReasoning).toEqual({});
  });

  it("reads back no stored pick for a role the researcher cannot pick", async () => {
    window.localStorage.setItem(
      "pathfinder-settings-20260625",
      JSON.stringify({
        state: {
          showRawToolCalls: true,
          showTokenUsage: true,
          deleteFromWdk: false,
          firstRunHintDismissed: true,
          phaseModels: { lead: OPENAI_FLAGSHIP.id, execution: ANTHROPIC_SMALL.id },
          phaseReasoning: { lead: "high", execution: "low" },
        },
        version: 0,
      }),
    );

    await useSettingsStore.persist.rehydrate();

    const s = useSettingsStore.getState();
    expect(s.phaseModels).toEqual({ lead: OPENAI_FLAGSHIP.id });
    expect(s.phaseReasoning).toEqual({ lead: "high" });
    expect(s.showRawToolCalls).toBe(true);
    expect(s.firstRunHintDismissed).toBe(true);
  });

  it("resetAllPersistedSettings removes the stored model picks", () => {
    useSettingsStore.getState().setPhaseModel("lead", OPENAI_FLAGSHIP.id);
    expect(window.localStorage.getItem("pathfinder-settings-20260625")).toContain(
      OPENAI_FLAGSHIP.id,
    );

    resetAllPersistedSettings();

    expect(
      Object.keys(window.localStorage).filter((key) => key.startsWith("pathfinder-")),
    ).toEqual([]);
  });
});
