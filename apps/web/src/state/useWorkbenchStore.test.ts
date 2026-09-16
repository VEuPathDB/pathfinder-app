// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import type { Experiment } from "@pathfinder/shared";

import { useWorkbenchStore } from "./useWorkbenchStore";

function makeExperiment(id: string): Experiment {
  return { id } as unknown as Experiment;
}

beforeEach(() => {
  useWorkbenchStore.getState().reset();
});

describe("useWorkbenchStore - gene set selection", () => {
  it("starts from a clean initial state", () => {
    const s = useWorkbenchStore.getState();
    expect(s.activeSetId).toBeNull();
    expect(s.selectedSetIds).toEqual([]);
    expect(s.expandedPanels.size).toBe(0);
    expect(s.leftSidebarOpen).toBe(true);
    expect(s.geneSearchOpen).toBe(false);
  });

  it("setActiveSet sets the active id and clears a stale experiment", () => {
    const s = useWorkbenchStore.getState();
    s.setLastExperiment(makeExperiment("e1"), "setA");
    s.setActiveSet("setA"); // same set -> keeps experiment
    expect(useWorkbenchStore.getState().activeSetId).toBe("setA");
    expect(useWorkbenchStore.getState().lastExperiment).not.toBeNull();

    s.setActiveSet("setB"); // different set -> clears experiment
    expect(useWorkbenchStore.getState().activeSetId).toBe("setB");
    expect(useWorkbenchStore.getState().lastExperiment).toBeNull();
    expect(useWorkbenchStore.getState().lastExperimentSetId).toBeNull();
  });

  it("toggleSetSelection adds then removes an id", () => {
    const s = useWorkbenchStore.getState();
    s.toggleSetSelection("a");
    s.toggleSetSelection("b");
    expect(useWorkbenchStore.getState().selectedSetIds).toEqual(["a", "b"]);
    s.toggleSetSelection("a");
    expect(useWorkbenchStore.getState().selectedSetIds).toEqual(["b"]);
  });

  it("selectAll / clearSelection / deselectAll manage the selection list", () => {
    const s = useWorkbenchStore.getState();
    s.selectAll(["a", "b", "c"]);
    expect(useWorkbenchStore.getState().selectedSetIds).toEqual(["a", "b", "c"]);
    s.clearSelection();
    expect(useWorkbenchStore.getState().selectedSetIds).toEqual([]);
    s.selectAll(["x"]);
    s.deselectAll();
    expect(useWorkbenchStore.getState().selectedSetIds).toEqual([]);
  });
});

describe("useWorkbenchStore - panels", () => {
  it("togglePanel adds then removes a panel", () => {
    const s = useWorkbenchStore.getState();
    s.togglePanel("enrichment");
    expect(useWorkbenchStore.getState().expandedPanels.has("enrichment")).toBe(true);
    s.togglePanel("enrichment");
    expect(useWorkbenchStore.getState().expandedPanels.has("enrichment")).toBe(false);
  });

  it("expandPanel is idempotent and collapsePanel removes", () => {
    const s = useWorkbenchStore.getState();
    s.expandPanel("ensemble");
    s.expandPanel("ensemble"); // no-op second time
    expect(useWorkbenchStore.getState().expandedPanels.has("ensemble")).toBe(true);
    expect(useWorkbenchStore.getState().expandedPanels.size).toBe(1);
    s.collapsePanel("ensemble");
    expect(useWorkbenchStore.getState().expandedPanels.has("ensemble")).toBe(false);
    s.collapsePanel("ensemble"); // no-op when absent
    expect(useWorkbenchStore.getState().expandedPanels.size).toBe(0);
  });
});

describe("useWorkbenchStore - sidebar + controls + experiment", () => {
  it("toggleGeneSearch and toggleLeftSidebar flip their flags", () => {
    const s = useWorkbenchStore.getState();
    s.toggleGeneSearch();
    expect(useWorkbenchStore.getState().geneSearchOpen).toBe(true);
    s.toggleLeftSidebar();
    expect(useWorkbenchStore.getState().leftSidebarOpen).toBe(false);
  });

  it("set/append positive and negative controls", () => {
    const s = useWorkbenchStore.getState();
    s.setPositiveControls(["p1"]);
    s.appendPositiveControls(["p2", "p3"]);
    expect(useWorkbenchStore.getState().positiveControls).toEqual(["p1", "p2", "p3"]);
    s.setNegativeControls(["n1"]);
    s.appendNegativeControls(["n2"]);
    expect(useWorkbenchStore.getState().negativeControls).toEqual(["n1", "n2"]);
  });

  it("setLastExperiment / clearLastExperiment manage the cached experiment", () => {
    const s = useWorkbenchStore.getState();
    s.setLastExperiment(makeExperiment("e9"), "setZ");
    expect(useWorkbenchStore.getState().lastExperiment?.id).toBe("e9");
    expect(useWorkbenchStore.getState().lastExperimentSetId).toBe("setZ");
    s.clearLastExperiment();
    expect(useWorkbenchStore.getState().lastExperiment).toBeNull();
    expect(useWorkbenchStore.getState().lastExperimentSetId).toBeNull();
  });

  it("reset restores every field to its initial value", () => {
    const s = useWorkbenchStore.getState();
    s.setActiveSet("a");
    s.selectAll(["a", "b"]);
    s.expandPanel("sweep");
    s.toggleGeneSearch();
    s.setPositiveControls(["p"]);
    s.reset();
    const r = useWorkbenchStore.getState();
    expect(r.activeSetId).toBeNull();
    expect(r.selectedSetIds).toEqual([]);
    expect(r.expandedPanels.size).toBe(0);
    expect(r.geneSearchOpen).toBe(false);
    expect(r.leftSidebarOpen).toBe(true);
    expect(r.positiveControls).toEqual([]);
  });
});
