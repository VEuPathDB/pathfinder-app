// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import {
  RIGHT_RAIL_PANELS,
  lastSeenFor,
  retiredPanel,
  useRightRailStore,
  useLeftSidebarStore,
  useSideOrderStore,
} from "./useRightRailStore";

beforeEach(() => {
  useRightRailStore.setState({
    openPanel: null,
    autoOpenedConversation: null,
    lastSeen: {},
  });
  useLeftSidebarStore.setState({ collapsed: false });
});

describe("RIGHT_RAIL_PANELS", () => {
  it("carries strategy, review and study", () => {
    expect(RIGHT_RAIL_PANELS).toEqual(["strategy", "review", "study"]);
  });
});

describe("retiredPanel", () => {
  it("maps a retired panel id", () => {
    expect(
      ["ledger", "tasks", "memories", "scratchpad", "eda", "strategy", "bogus", 3].map(
        retiredPanel,
      ),
    ).toEqual([
      "review",
      "review",
      "review",
      "review",
      "study",
      "strategy",
      null,
      null,
    ]);
  });

  it("hydrates a stored retired panel as its successor", async () => {
    window.localStorage.setItem(
      useRightRailStore.persist.getOptions().name ?? "",
      JSON.stringify({ state: { openPanel: "tasks", lastSeen: {} }, version: 0 }),
    );

    await useRightRailStore.persist.rehydrate();

    expect(useRightRailStore.getState().openPanel).toBe("review");
  });
});

describe("useRightRailStore", () => {
  it("openPanelId opens a panel and merges last-seen markers for that conversation", () => {
    useRightRailStore
      .getState()
      .openPanelId("c1", "strategy", { strategyStepCount: 4 });
    const s = useRightRailStore.getState();
    expect(s.openPanel).toBe("strategy");
    expect(lastSeenFor(s.lastSeen, "c1").strategyStepCount).toBe(4);
    expect(lastSeenFor(s.lastSeen, "c1").reviewCount).toBe(0);
  });

  it("keeps one conversation's markers out of another's", () => {
    useRightRailStore.getState().openPanelId("c1", "review", { reviewCount: 3 });
    const seen = useRightRailStore.getState().lastSeen;
    expect(lastSeenFor(seen, "c1").reviewCount).toBe(3);
    expect(lastSeenFor(seen, "c2").reviewCount).toBe(0);
  });

  it("openPanelId records the study marker so the dot clears", () => {
    useRightRailStore.getState().openPanelId("c1", "study", { studyCount: 3 });
    const s = useRightRailStore.getState();
    expect(s.openPanel).toBe("study");
    expect(lastSeenFor(s.lastSeen, "c1").studyCount).toBe(3);
  });

  it("togglePanel opens a different panel, closes the same one", () => {
    const s = useRightRailStore.getState();
    s.togglePanel("c1", "review", { reviewCount: 1 });
    expect(useRightRailStore.getState().openPanel).toBe("review");
    expect(lastSeenFor(useRightRailStore.getState().lastSeen, "c1").reviewCount).toBe(
      1,
    );

    s.togglePanel("c1", "review", { reviewCount: 2 });
    expect(useRightRailStore.getState().openPanel).toBeNull();

    s.togglePanel("c1", "strategy", {});
    expect(useRightRailStore.getState().openPanel).toBe("strategy");
  });

  it("closePanel clears the open panel", () => {
    useRightRailStore.getState().openPanelId("c1", "review", {});
    useRightRailStore.getState().closePanel();
    expect(useRightRailStore.getState().openPanel).toBe(null);
  });

  it("autoOpen opens review once per conversation", () => {
    useRightRailStore.getState().autoOpen("c1", "review");
    expect(useRightRailStore.getState().openPanel).toBe("review");
    expect(useRightRailStore.getState().autoOpenedConversation).toBe("c1");
  });

  it("autoOpen leaves a panel the researcher already opened", () => {
    useRightRailStore.getState().togglePanel("c1", "strategy", {});
    useRightRailStore.getState().autoOpen("c1", "review");
    expect(useRightRailStore.getState().openPanel).toBe("strategy");
  });

  it("autoOpen runs again on another conversation", () => {
    useRightRailStore.getState().closePanel();
    useRightRailStore.getState().autoOpen("c2", "review");
    expect(useRightRailStore.getState().openPanel).toBe("review");
  });
});

describe("the side opened last", () => {
  it("follows whichever side opened most recently", () => {
    useLeftSidebarStore.setState({ collapsed: true });
    useRightRailStore.getState().togglePanel("c1", "review", {});
    const afterRight = useSideOrderStore.getState().lastOpened;
    useLeftSidebarStore.getState().toggle();
    const afterLeft = useSideOrderStore.getState().lastOpened;
    useRightRailStore.getState().openPanelId("c1", "strategy", {});

    expect([afterRight, afterLeft, useSideOrderStore.getState().lastOpened]).toEqual([
      "right",
      "left",
      "right",
    ]);
  });

  it("is not moved by closing a side", () => {
    useRightRailStore.getState().togglePanel("c1", "review", {});
    useLeftSidebarStore.getState().setCollapsed(false);
    useRightRailStore.getState().closePanel();

    expect(useSideOrderStore.getState().lastOpened).toBe("left");
  });
});

describe("useLeftSidebarStore", () => {
  it("keeps the sidebar's width", () => {
    useLeftSidebarStore.getState().setWidth(280);
    expect(useLeftSidebarStore.getState().width).toBe(280);
  });

  it("toggles and sets collapsed", () => {
    useLeftSidebarStore.getState().toggle();
    expect(useLeftSidebarStore.getState().collapsed).toBe(true);
    useLeftSidebarStore.getState().setCollapsed(false);
    expect(useLeftSidebarStore.getState().collapsed).toBe(false);
  });
});
